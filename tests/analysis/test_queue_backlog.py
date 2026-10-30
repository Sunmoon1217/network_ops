"""积压明细（analysis.queue_monitor.collect_backlog + manage.py queue_backlog）：

与 test_queue_monitor 的「数量 + 告警」互补，这里对账「积压了哪些」的三段清单：
队列排队消息（broker JSON + base64 解码）、Stream PEL（重投排序、点名设备）、
Stream 未投递（lag 口径：只翻 last-delivered 之后的，不把已消费未 trim 的翻出来）。
不碰真实 Redis：假 client 只实现 lrange / xpending_range / xrange / xinfo_groups。
"""

import base64
import json

import pytest
from django.core.management import call_command

from analysis.access_stream import GROUP
from analysis.queue_monitor import collect_backlog


def broker_message(task: str, task_id: str, args) -> bytes:
    """构造 celery broker 消息（JSON envelope + base64 body），与真实投递同形。"""
    body = base64.b64encode(json.dumps([args, {}, None]).encode()).decode()
    return json.dumps({"headers": {"task": task, "id": task_id}, "body": body}).encode()


class FakeRedis:
    """只实现 collect_backlog 用到的命令；抛 Exception 模拟 Redis 不可达。"""

    def __init__(self, *, queues=None, pending=None, undelivered=None, last_delivered="0-0", groups=True):
        self.queues = queues or {}  # name -> [bytes]
        self.pending = pending or []  # xpending_range 返回形
        self.undelivered = undelivered or []  # [(id, fields)]，XRANGE 的积压段
        self.last_delivered = last_delivered
        self.groups = groups  # False → xinfo_groups 抛错
        self.xrange_calls = []

    def lrange(self, name, start, end):
        return self.queues.get(name, [])[start : end + 1]

    def xpending_range(self, stream, group, min, max, count):
        return self.pending[:count]

    def xinfo_groups(self, stream):
        if not self.groups:
            raise LookupError("no such key")
        return [{"name": GROUP, "last-delivered": self.last_delivered, "lag": len(self.undelivered)}]

    def xrange(self, stream, min="-", max="+", count=None):
        self.xrange_calls.append(min)
        if min.startswith("("):
            rows = self.undelivered  # 积压段：fake 不做区间过滤，由调用方的 min 标记断言
        else:
            # 按 ID 精确取（_stream_entry 补设备名用）
            rows = [(i, f) for i, f in self.undelivered if i == min]
        return rows[:count] if count else rows


def _fields(device_id: int, hostname: str) -> dict:
    return {b"device_id": str(device_id).encode(), b"hostname": hostname.encode(), b"flows": b"[]"}


# ---------------------------------------------------------------------------
# 队列排队消息
# ---------------------------------------------------------------------------


def test_queue_entries_are_decoded():
    client = FakeRedis(
        queues={
            "celery": [
                broker_message("ingest.tasks.run_collection_stage", "id-1", [12]),
                broker_message("analysis.rebuild_access_flows", "id-2", ["NET-FW01"]),
            ]
        }
    )
    stats = collect_backlog(client=client, limit=20)
    assert stats["redis_ok"] is True
    items = stats["queues"]["celery"]
    assert [i["task"] for i in items] == ["ingest.tasks.run_collection_stage", "analysis.rebuild_access_flows"]
    assert items[0]["id"] == "id-1"
    assert items[0]["decode_error"] is False


def test_undecodable_message_falls_back_to_raw_preview():
    client = FakeRedis(queues={"celery": [b"\xff not json at all"]})
    stats = collect_backlog(client=client, limit=20)
    item = stats["queues"]["celery"][0]
    assert item["decode_error"] is True
    assert item["task"] is None
    assert item["args"]  # 原文预览兜底


def test_long_args_are_clipped():
    client = FakeRedis(queues={"celery": [broker_message("t", "id", ["x" * 500])]})
    stats = collect_backlog(client=client, limit=20)
    assert stats["queues"]["celery"][0]["args"].endswith("…")


def test_limit_caps_queue_entries():
    client = FakeRedis(queues={"celery": [broker_message("t", f"id-{i}", []) for i in range(30)]})
    stats = collect_backlog(client=client, limit=5)
    assert len(stats["queues"]["celery"]) == 5


# ---------------------------------------------------------------------------
# Stream 两段积压
# ---------------------------------------------------------------------------


def test_pending_sorted_by_deliveries_and_named_by_device():
    client = FakeRedis(
        pending=[
            {"message_id": "1-0", "time_since_delivered": 1000, "times_delivered": 1},
            {"message_id": "2-0", "time_since_delivered": 5000, "times_delivered": 9},
        ],
        undelivered=[("1-0", _fields(3, "NET-FW01")), ("2-0", _fields(4, "NET-FW02"))],
    )
    stats = collect_backlog(client=client, limit=20)
    pending = stats["stream"]["pending"]
    assert [p["id"] for p in pending] == ["2-0", "1-0"]  # 重投多的排前（毒消息先看到）
    assert pending[0]["deliveries"] == 9
    assert pending[0]["hostname"] == "NET-FW02"
    assert pending[0]["device_id"] == 4


def test_undelivered_uses_exclusive_last_delivered():
    """lag 口径：XRANGE 的 min 必须是 (last-delivered——已消费未 trim 的旧条目不进清单。"""
    client = FakeRedis(last_delivered="100-0", undelivered=[("101-0", _fields(5, "NET-FW03"))])
    stats = collect_backlog(client=client, limit=20)
    assert client.xrange_calls[0] == "(100-0"  # 排他区间标记
    assert stats["stream"]["undelivered"] == [{"id": "101-0", "device_id": 5, "hostname": "NET-FW03"}]


def test_missing_group_gives_empty_undelivered():
    client = FakeRedis(groups=False)
    stats = collect_backlog(client=client, limit=20)
    assert stats["stream"]["undelivered"] == []


def test_redis_down_degrades_not_crash():
    class Broken(FakeRedis):
        def lrange(self, name, start, end):
            raise ConnectionError("redis down")

    stats = collect_backlog(client=Broken(), limit=20)
    assert stats["redis_ok"] is False
    assert "redis down" in stats["error"]


# ---------------------------------------------------------------------------
# 命令
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_command_renders_three_sections(monkeypatch, capsys):
    client = FakeRedis(
        queues={"celery": [broker_message("ingest.tasks.x", "id-1", [1])]},
        pending=[{"message_id": "1-0", "time_since_delivered": 2000, "times_delivered": 11}],
        undelivered=[("2-0", _fields(3, "NET-FW01"))],
        last_delivered="1-0",
    )
    monkeypatch.setattr("analysis.queue_monitor.get_redis", lambda: client)
    call_command("queue_backlog")
    out = capsys.readouterr().out
    assert "ingest.tasks.x" in out  # 队列消息解码
    assert "已重投 11 次" in out  # PEL 点名
    assert "NET-FW01" in out  # 未投递段点名设备


@pytest.mark.django_db
def test_command_json_output(monkeypatch, capsys):
    monkeypatch.setattr("analysis.queue_monitor.get_redis", lambda: FakeRedis())
    call_command("queue_backlog", "--json", "--limit", "3")
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["limit"] == 3
    assert payload["stream"] == {"pending": [], "undelivered": []}


@pytest.mark.django_db
def test_command_renders_redis_outage(monkeypatch, capsys):
    class Broken(FakeRedis):
        def lrange(self, name, start, end):
            raise ConnectionError("redis down")

    monkeypatch.setattr("analysis.queue_monitor.get_redis", lambda: Broken())
    call_command("queue_backlog")  # 不抛异常，如实降级
    assert "Redis 不可达" in capsys.readouterr().out
