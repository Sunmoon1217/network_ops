"""运行监控（analysis.redis_monitor / analysis.celery_monitor）：采集口径、降级、API。

不碰真实 Redis / broker：Redis 侧假 client 只实现 info / dbsize；celery 侧假
inspector 只实现 ping / stats / active / reserved / scheduled。两条降级纪律对账：
采集自身不炸（ok=False + error），API 200 如实透传。
"""

import pytest
from rest_framework.authtoken.models import Token as DRFToken
from rest_framework.test import APIClient

from analysis.celery_monitor import collect as celery_collect
from analysis.redis_monitor import collect as redis_collect
from core.models import User

REDIS_API = "/api/analysis/redis-status/"
CELERY_API = "/api/analysis/celery-status/"


class FakeRedis:
    """只实现 redis_monitor 用到的命令（info / dbsize）；抛 Exception 模拟不可达。"""

    def __init__(self, *, info=None, dbsize=0):
        self._info = info or {}
        self._dbsize = dbsize

    def info(self):
        if isinstance(self._info, Exception):
            raise self._info
        return self._info

    def dbsize(self):
        return self._dbsize


class FakeInspector:
    """只实现 celery_monitor 用到的 inspect 方法；返回 None 模拟无 worker 应答。"""

    def __init__(self, *, ping=None, stats=None, active=None, reserved=None, scheduled=None):
        self._ping = ping
        self._stats = stats
        self._active = active
        self._reserved = reserved
        self._scheduled = scheduled

    def ping(self):
        return self._ping

    def stats(self):
        return self._stats

    def active(self):
        return self._active

    def reserved(self):
        return self._reserved

    def scheduled(self):
        return self._scheduled


def _redis_info(**overrides) -> dict:
    info = {
        "redis_version": "7.2.4",
        "redis_mode": "standalone",
        "uptime_in_seconds": 86400,
        "used_memory": 50_000_000,
        "used_memory_human": "47.68M",
        "used_memory_peak_human": "60.12M",
        "used_memory_rss_human": "52.00M",
        "mem_fragmentation_ratio": 1.09,
        "maxmemory": 100_000_000,
        "maxmemory_human": "95.37M",
        "connected_clients": 12,
        "blocked_clients": 1,
        "maxclients": 10000,
        "instantaneous_ops_per_sec": 230,
        "total_commands_processed": 1_234_567,
        "keyspace_hits": 90,
        "keyspace_misses": 10,
        "evicted_keys": 0,
        "expired_keys": 300,
        "db0": {"keys": 1200, "expires": 30},
    }
    info.update(overrides)
    return info


# ---------------------------------------------------------------------------
# Redis：采集口径
# ---------------------------------------------------------------------------


def test_redis_collect_healthy_shape():
    stats = redis_collect(client=FakeRedis(info=_redis_info(), dbsize=1200))
    assert stats["redis_ok"] is True
    assert stats["server"]["version"] == "7.2.4"
    assert stats["memory"]["used_ratio"] == 0.5  # 50M/100M
    assert stats["clients"] == {"connected": 12, "blocked": 1, "maxclients": 10000}
    assert stats["stats"]["hit_rate"] == 0.9  # 90/(90+10)
    assert stats["keyspace"]["total_keys"] == 1200
    assert stats["keyspace"]["dbsize"] == 1200


def test_redis_maxmemory_zero_gives_null_ratio():
    """maxmemory=0（不限制）时使用率是 null 而不是 0——「不限」不是「空」。"""
    stats = redis_collect(client=FakeRedis(info=_redis_info(maxmemory=0)))
    assert stats["memory"]["used_ratio"] is None


def test_redis_zero_traffic_gives_null_hit_rate():
    """hits/misses 皆 0（没跑过读）时命中率 null 而不是 0。"""
    stats = redis_collect(client=FakeRedis(info=_redis_info(keyspace_hits=0, keyspace_misses=0)))
    assert stats["stats"]["hit_rate"] is None


def test_redis_unreachable_degrades_not_crashes():
    stats = redis_collect(client=FakeRedis(info=ConnectionError("redis down")))
    assert stats["redis_ok"] is False
    assert "redis down" in stats["error"]


def test_redis_keyspace_sums_multiple_dbs():
    info = _redis_info()
    del info["db0"]
    info["db0"] = {"keys": 100, "expires": 5}
    info["db1"] = {"keys": 200, "expires": 0}
    stats = redis_collect(client=FakeRedis(info=info, dbsize=300))
    assert stats["keyspace"]["total_keys"] == 300
    assert stats["keyspace"]["dbs"] == {"db0": {"keys": 100, "expires": 5}, "db1": {"keys": 200, "expires": 0}}


# ---------------------------------------------------------------------------
# Celery：采集口径
# ---------------------------------------------------------------------------


def test_celery_collect_healthy_shape():
    inspector = FakeInspector(
        ping={"celery@worker1": {"ok": "pong"}},
        stats={"celery@worker1": {"pool": {"max-concurrency": 2}, "total": {"ingest.tasks.x": 10, "ingest.tasks.y": 5}}},
        active={
            "celery@worker1": [
                {"id": "t1", "name": "ingest.tasks.x", "args": "[1]", "kwargs": "{}", "hostname": "celery@worker1", "time_start": 100.0},
            ]
        },
        reserved={"celery@worker1": [{"id": "t2", "name": "ingest.tasks.y", "args": "[]", "kwargs": "{}"}]},
        scheduled={"celery@worker1": [{"eta": "2026-01-01T00:00:00", "request": {"id": "t3", "name": "ingest.tasks.z"}}]},
    )
    stats = celery_collect(inspector=inspector)
    assert stats["ok"] is True
    assert stats["workers"] == [{"name": "celery@worker1", "concurrency": 2, "processed": 15, "status": "online"}]
    assert stats["active"][0]["id"] == "t1"
    assert stats["active"][0]["worker"] == "celery@worker1"
    assert stats["reserved"][0]["id"] == "t2"
    assert stats["scheduled"][0]["id"] == "t3"
    assert stats["scheduled"][0]["eta"] == "2026-01-01T00:00:00"


def test_celery_no_worker_is_degraded_not_crash():
    stats = celery_collect(inspector=FakeInspector(ping=None))
    assert stats["ok"] is False
    assert "没有 worker 应答" in stats["error"]
    assert stats["workers"] == []


def test_celery_long_args_are_clipped():
    inspector = FakeInspector(
        ping={"w": {"ok": "pong"}},
        active={"w": [{"id": "t1", "name": "x", "args": "a" * 500, "kwargs": "{}"}]},
    )
    stats = celery_collect(inspector=inspector)
    assert len(stats["active"][0]["args"]) == 201  # 200 + 省略号
    assert stats["active"][0]["args"].endswith("…")


def test_celery_partial_inspect_failure_degrades_gracefully():
    """一段 inspect 挂掉不影响其余段；整体 ok 仍为 True（worker 还应答）。"""

    class Flaky(FakeInspector):
        def active(self):
            raise ConnectionError("boom")

    inspector = Flaky(ping={"w": {"ok": "pong"}}, stats={"w": {"pool": {"max-concurrency": 1}, "total": {}}})
    stats = celery_collect(inspector=inspector)
    assert stats["ok"] is True  # worker 应答了，只是 active 拿不到
    assert stats["active"] == []
    assert stats["workers"][0]["name"] == "w"


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client(db):
    user = User.objects.create_user(username="_t_runtime_monitor", password="pw-runtime-1")
    token = DRFToken.objects.create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


@pytest.mark.django_db
def test_redis_status_api_returns_collect_shape(api_client, monkeypatch):
    monkeypatch.setattr("analysis.redis_monitor.get_redis", lambda: FakeRedis(info=_redis_info(), dbsize=1200))
    resp = api_client.get(REDIS_API)
    assert resp.status_code == 200
    body = resp.json()
    assert body["redis_ok"] is True
    assert body["memory"]["used_ratio"] == 0.5


@pytest.mark.django_db
def test_celery_status_api_returns_collect_shape(api_client, monkeypatch):
    monkeypatch.setattr(
        "analysis.celery_monitor.celery_app.control.inspect",
        lambda timeout: FakeInspector(ping={"w": {"ok": "pong"}}, stats={"w": {"pool": {"max-concurrency": 2}, "total": {}}}),
    )
    resp = api_client.get(CELERY_API)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["workers"][0]["concurrency"] == 2


@pytest.mark.django_db
def test_monitor_apis_require_auth(monkeypatch):
    monkeypatch.setattr("analysis.redis_monitor.get_redis", lambda: FakeRedis(info=_redis_info()))
    monkeypatch.setattr("analysis.celery_monitor.celery_app.control.inspect", lambda timeout: FakeInspector(ping=None))
    assert APIClient().get(REDIS_API).status_code == 401
    assert APIClient().get(CELERY_API).status_code == 401


@pytest.mark.django_db
def test_monitor_apis_surface_outage_without_500(api_client, monkeypatch):
    """Redis / broker 都挂时 API 照样 200（ok=False 如实上报），监控自身不炸。"""
    monkeypatch.setattr("analysis.redis_monitor.get_redis", lambda: FakeRedis(info=ConnectionError("redis down")))
    monkeypatch.setattr("analysis.celery_monitor.celery_app.control.inspect", lambda timeout: FakeInspector(ping=None))
    assert api_client.get(REDIS_API).json()["redis_ok"] is False
    assert api_client.get(CELERY_API).json()["ok"] is False
