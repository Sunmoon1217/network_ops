"""队列积压巡检（analysis.queue_monitor）：采集口径、告警阈值、命令退出码、API。

不碰真实 Redis：全部用假 client（与 test_access_stream 的做法一致）——巡检是只读的，
假 client 只需要实现 collect 用到的几个方法（llen / hlen / xlen / xinfo_groups /
xpending_range / get）。背压口径（backlog 用 lag 而非 XLEN）也在这里对账。
"""

import json
import time

import pytest
from django.core.management import call_command
from rest_framework.authtoken.models import Token as DRFToken
from rest_framework.test import APIClient

from analysis.access_stream import GROUP, backlog
from analysis.queue_monitor import DEFAULT_THRESHOLDS, collect, evaluate
from core.models import User

API_URL = "/api/analysis/queue-status/"


class FakeRedis:
    """只实现巡检/背压用到的命令；任何方法抛 Exception 即模拟 Redis 不可达。"""

    def __init__(
        self,
        *,
        queues=None,
        unacked=0,
        xlen=0,
        groups=None,
        pending_entries=None,
        heartbeat=None,
    ):
        self.queues = queues or {}
        self.unacked = unacked
        self.xlen_value = xlen
        self.groups = groups  # None → xinfo_groups 抛错（键不存在）
        self.pending_entries = pending_entries or []
        self.heartbeat = heartbeat  # bytes 时间戳 / None / Exception

    def llen(self, name):
        return self.queues.get(name, 0)

    def hlen(self, name):
        return self.unacked

    def xlen(self, name):
        return self.xlen_value

    def xinfo_groups(self, stream):
        if self.groups is None:
            raise LookupError("no such key")
        return self.groups

    def xpending_range(self, stream, group, min, max, count):
        return self.pending_entries

    def get(self, key):
        if isinstance(self.heartbeat, Exception):
            raise self.heartbeat
        return self.heartbeat


def _group_info(*, lag=0, pending=0, consumers=1, name=GROUP):
    return {"name": name, "lag": lag, "pending": pending, "consumers": consumers}


def _healthy_client(**overrides) -> FakeRedis:
    defaults = {
        "queues": {"celery": 0, "access_flow": 0},
        "unacked": 2,
        "xlen": 47,
        "groups": [_group_info(lag=0, pending=0)],
        "heartbeat": str(time.time() - 3).encode(),
    }
    defaults.update(overrides)
    return FakeRedis(**defaults)


# ---------------------------------------------------------------------------
# 采集口径
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_collect_healthy_shape():
    stats = collect(client=_healthy_client())

    assert stats["redis_ok"] is True
    # 队列名来自 CELERY_TASK_ROUTES + 默认 celery
    assert stats["queues"] == {"access_flow": 0, "celery": 0}
    assert stats["unacked"] == 2
    assert stats["stream"]["xlen"] == 47
    assert stats["stream"]["lag"] == 0
    assert stats["stream"]["pending"] == 0
    assert stats["heartbeat_age"] is not None and stats["heartbeat_age"] < 10
    assert stats["alerts"] == []


@pytest.mark.django_db
def test_collect_ignores_foreign_groups_and_missing_key():
    """组列表里有别的组要跳过；Stream 键不存在（xinfo 抛错）按全零处理、不算故障。"""
    client = _healthy_client(groups=[_group_info(name="other-group", lag=999)])
    stats = collect(client=client)
    assert stats["redis_ok"] is True
    assert stats["stream"]["lag"] is None
    assert stats["stream"]["pending"] == 0
    # lag 未知 → 退回 xlen 估算，xlen=0 无告警
    assert stats["alerts"] == []

    client = _healthy_client(groups=None, xlen=0, heartbeat=None)
    stats = collect(client=client)
    assert stats["redis_ok"] is True
    # 心跳缺失是 critical（consumer 没在跑）
    codes = {a["code"] for a in stats["alerts"]}
    assert "heartbeat_missing" in codes


@pytest.mark.django_db
def test_collect_top_pending_sorted_by_deliveries():
    entries = [
        {"message_id": "1-0", "consumer": "a", "time_since_delivered": 1000, "times_delivered": 2},
        {"message_id": "2-0", "consumer": "a", "time_since_delivered": 2000, "times_delivered": 13},
        {"message_id": "3-0", "consumer": "a", "time_since_delivered": 3000, "times_delivered": 7},
    ]
    client = _healthy_client(groups=[_group_info(lag=0, pending=3)], pending_entries=entries)
    stats = collect(client=client)

    top = stats["stream"]["top_pending"]
    assert [e["deliveries"] for e in top] == [13, 7, 2]
    assert top[0]["id"] == "2-0"
    # 重投 13 次 ≥ 阈值 10 → 毒消息 critical
    poison = [a for a in stats["alerts"] if a["code"] == "poison_message"]
    assert len(poison) == 1 and "2-0" in poison[0]["message"]


@pytest.mark.django_db
def test_collect_redis_down_is_critical_not_crash():
    class Broken(FakeRedis):
        def llen(self, name):
            raise ConnectionError("redis down")

    stats = collect(client=Broken())
    assert stats["redis_ok"] is False
    assert "redis down" in stats["error"]
    assert stats["alerts"][0]["code"] == "redis_unreachable"
    assert stats["alerts"][0]["level"] == "critical"


# ---------------------------------------------------------------------------
# 阈值告警
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_evaluate_thresholds_fire_and_pass():
    # 队列积压
    stats = collect(client=_healthy_client(queues={"celery": 1500, "access_flow": 0}))
    codes = {a["code"] for a in stats["alerts"]}
    assert "queue_backlog" in codes

    # unacked 高（worker 死了任务滞留）
    stats = collect(client=_healthy_client(unacked=300))
    codes = {a["code"] for a in stats["alerts"]}
    assert "unacked_high" in codes

    # Stream 未消费积压（lag 口径，xlen 高但 lag=0 不告警）
    stats = collect(client=_healthy_client(groups=[_group_info(lag=500, pending=0)]))
    codes = {a["code"] for a in stats["alerts"]}
    assert "stream_backlog" in codes

    # PEL 高
    stats = collect(client=_healthy_client(groups=[_group_info(lag=0, pending=80)]))
    codes = {a["code"] for a in stats["alerts"]}
    assert "stream_pending" in codes

    # 心跳过期
    stats = collect(client=_healthy_client(heartbeat=str(time.time() - 700).encode()))
    codes = {a["code"] for a in stats["alerts"]}
    assert "heartbeat_stale" in codes

    # 阈值可覆盖：默认会告警的值，抬高阈值后安静
    stats = collect(client=_healthy_client(queues={"celery": 1500}), thresholds={"max_queue": 2000})
    assert stats["alerts"] == []


@pytest.mark.django_db
def test_evaluate_uses_embedded_thresholds_from_collect():
    """collect 把 thresholds 存进 stats，evaluate 无参调用也按同一套阈值。"""
    stats = collect(client=_healthy_client(queues={"celery": 1500}), thresholds={"max_queue": 1000})
    assert evaluate(stats) == stats["alerts"]
    assert DEFAULT_THRESHOLDS["max_queue"] == 1000  # 默认值锚点：改默认值要同步文档


# ---------------------------------------------------------------------------
# 背压口径（backlog 用 lag，不是 XLEN）
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_backlog_uses_group_lag_not_xlen(monkeypatch):
    """XLEN 含已消费未 trim 的条目；背压必须看 lag——消化完的积压不算积压。"""
    client = _healthy_client(xlen=1800, groups=[_group_info(lag=0)])
    monkeypatch.setattr("analysis.access_stream.get_redis", lambda: client)
    assert backlog() == 0

    client = _healthy_client(xlen=1800, groups=[_group_info(lag=42)])
    monkeypatch.setattr("analysis.access_stream.get_redis", lambda: client)
    assert backlog() == 42


@pytest.mark.django_db
def test_backlog_fallbacks_and_degrades_gracefully(monkeypatch):
    # lag 未知（trim 过）→ 退回 XLEN
    client = _healthy_client(xlen=1800, groups=[{"name": GROUP, "lag": None, "pending": 0, "consumers": 1}])
    monkeypatch.setattr("analysis.access_stream.get_redis", lambda: client)
    assert backlog() == 1800

    # 组不存在 → 0
    client = _healthy_client(groups=None)
    monkeypatch.setattr("analysis.access_stream.get_redis", lambda: client)
    assert backlog() == 0

    # Redis 不可达 → 0（不背压，失败留给投递处暴露）
    class Broken(FakeRedis):
        def xinfo_groups(self, stream):
            raise ConnectionError("redis down")

    monkeypatch.setattr("analysis.access_stream.get_redis", lambda: Broken())
    assert backlog() == 0


# ---------------------------------------------------------------------------
# 命令退出码
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_command_exits_zero_when_healthy(monkeypatch, capsys):
    monkeypatch.setattr("analysis.queue_monitor.get_redis", lambda: _healthy_client())
    call_command("queue_status")
    out = capsys.readouterr().out
    assert "celery 队列" in out and "访问流 Stream" in out


@pytest.mark.django_db
def test_command_json_output_and_exit_one_on_alert(monkeypatch, capsys):
    client = _healthy_client(queues={"celery": 1500}, groups=[_group_info(lag=500, pending=80)])
    monkeypatch.setattr("analysis.queue_monitor.get_redis", lambda: client)
    with pytest.raises(SystemExit) as exc:
        call_command("queue_status", "--json")
    assert exc.value.code == 1
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[0])
    codes = {a["code"] for a in payload["alerts"]}
    assert {"queue_backlog", "stream_backlog", "stream_pending"} <= codes


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client(db):
    user = User.objects.create_user(username="_t_queue_monitor", password="pw-queue-1")
    token = DRFToken.objects.create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


@pytest.mark.django_db
def test_queue_status_api_returns_collect_shape(api_client, monkeypatch):
    monkeypatch.setattr("analysis.queue_monitor.get_redis", lambda: _healthy_client())
    resp = api_client.get(API_URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["redis_ok"] is True
    assert set(body["queues"]) == {"celery", "access_flow"}
    assert body["stream"]["lag"] == 0
    assert body["alerts"] == []


@pytest.mark.django_db
def test_queue_status_api_requires_auth(monkeypatch):
    monkeypatch.setattr("analysis.queue_monitor.get_redis", lambda: _healthy_client())
    resp = APIClient().get(API_URL)
    assert resp.status_code == 401


@pytest.mark.django_db
def test_queue_status_api_surfaces_redis_outage(api_client, monkeypatch):
    class Broken(FakeRedis):
        def llen(self, name):
            raise ConnectionError("redis down")

    monkeypatch.setattr("analysis.queue_monitor.get_redis", lambda: Broken())
    resp = api_client.get(API_URL)
    assert resp.status_code == 200  # 巡检自身不炸：redis_ok=False + critical 告警
    body = resp.json()
    assert body["redis_ok"] is False
    assert body["alerts"][0]["code"] == "redis_unreachable"
