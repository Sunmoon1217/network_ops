"""链路缓存：分桶、脱敏、失败隔离与 Redis 写入 / 读取。"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import redis
from django.conf import settings

from ingest.collectors import link_cache
from ingest.collectors.link_config import parse_links_config
from ingest.collectors.zabbix import queries

NOW = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)


def _config(*, enabled: bool = True):
    return parse_links_config(
        {
            "version": 1,
            "panels": [{"id": "internet", "label": "互联网链路", "scopes": ["ipv4"]}],
            "scopes": {"ipv4": "IPv4 互联网链路"},
            "targets": [
                {"scope": "ipv4", "subject": "zjbgp", "label": "中金BGP", "host": "h1", "ifname": "eth0", "enabled": enabled},
                {"scope": "ipv4", "subject": "jxqcu", "label": "世纪互联联通", "host": "h2", "ifname": "eth1", "enabled": enabled},
            ],
        }
    )


def test_build_payload_buckets_and_keeps_max():
    config = _config()
    base = int(NOW.timestamp())
    samples = {
        "h1": [(base - 180, 10.0), (base - 179, 40.0), (base - 360, 5.0)],
        "h2": [(base - 180, 30.0)],
    }

    async def fake_history(host, ifname, *, time_from, time_till):
        return samples[host]

    with patch.object(queries, "link_history", new=AsyncMock(side_effect=fake_history)):
        payload = asyncio.run(link_cache.build_link_payload(config, window_hours=3, now=NOW))

    assert payload["refreshed_at"] == NOW.isoformat()
    assert payload["window_hours"] == 3
    assert len(payload["points"]) == 2
    latest = {point["time"]: point["data"] for point in payload["points"]}[link_cache._time_label(base - 180)]
    assert latest["ipv4"] == {"zjbgp": 40.0, "jxqcu": 30.0}
    assert "host" not in payload["targets"][0]
    assert "ifname" not in payload["targets"][0]


def test_build_payload_isolates_single_failure():
    config = _config()
    base = int(NOW.timestamp())

    async def fake_history(host, ifname, *, time_from, time_till):
        if host == "h1":
            raise RuntimeError("boom")
        return [(base - 180, 30.0)]

    with patch.object(queries, "link_history", new=AsyncMock(side_effect=fake_history)):
        payload = asyncio.run(link_cache.build_link_payload(config, now=NOW))

    assert payload["points"][0]["data"] == {"ipv4": {"jxqcu": 30.0}}


def test_build_payload_raises_when_all_fail():
    with patch.object(queries, "link_history", new=AsyncMock(side_effect=RuntimeError("boom"))):
        with pytest.raises(RuntimeError, match="全部链路采集失败"):
            asyncio.run(link_cache.build_link_payload(_config(), now=NOW))


def test_build_payload_skips_all_disabled():
    with patch.object(queries, "link_history", new=AsyncMock()) as mocked:
        payload = asyncio.run(link_cache.build_link_payload(_config(enabled=False), now=NOW))
    assert payload["points"] == []
    mocked.assert_not_called()


def test_refresh_writes_json_with_ttl():
    client = MagicMock()
    payload = {"points": [], "targets": [], "refreshed_at": "2026-11-11T10:00:00+00:00", "panels": [], "scopes": {}, "window_hours": 3}
    with patch.object(link_cache, "build_link_payload", new=AsyncMock(return_value=payload)):
        summary = link_cache.refresh_link_cache(_config(), client=client)

    args, kwargs = client.set.call_args
    assert args[0] == settings.DASHBOARD_LINK_CACHE_KEY
    assert kwargs["ex"] == settings.DASHBOARD_LINK_CACHE_TTL
    assert summary == {"points": 0, "targets": 0, "refreshed_at": payload["refreshed_at"]}


def test_read_returns_none_on_miss_and_bad_json():
    client = MagicMock()
    client.get.return_value = None
    assert link_cache.read_link_cache(client=client) is None

    client.get.return_value = b"{"
    assert link_cache.read_link_cache(client=client) is None

    client.get.return_value = b'{"points": []}'
    assert link_cache.read_link_cache(client=client) == {"points": []}


def test_read_returns_none_when_redis_unavailable():
    client = MagicMock()
    client.get.side_effect = redis.RedisError("down")
    assert link_cache.read_link_cache(client=client) is None


def test_link_history_returns_clock_value_pairs():
    zapi = MagicMock()
    zapi.history_get = AsyncMock(
        return_value=[
            MagicMock(clock="1000", value="12.5"),
            MagicMock(clock="1060", value="bad"),
            MagicMock(clock="1120", value="8"),
        ]
    )
    with (
        patch.object(queries, "_link_items", new=AsyncMock(return_value=[MagicMock(itemid="1")])),
        patch.object(queries, "get_zapi", new=AsyncMock(return_value=zapi)),
    ):
        rows = asyncio.run(queries.link_history("h", "e", time_from=0, time_till=2000))

    assert rows == [(1000, 12.5), (1120, 8.0)]
