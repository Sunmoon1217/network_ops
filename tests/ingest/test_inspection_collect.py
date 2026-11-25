"""巡检采集：方向识别、按天聚合、默认日期与失败隔离（全部 mock Zabbix）。"""

import asyncio
from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from django.utils import timezone

from core.integrations.providers.zabbix.schemas import ZAPIHistory, ZAPIHost, ZAPIItem
from ingest.collectors import inspection
from ingest.collectors.zabbix import queries


def _item(itemid, key_, name, host="SW-1"):
    return ZAPIItem(itemid=itemid, key_=key_, name=name, hosts=[ZAPIHost(hostid="1", host=host, name=host)])


def _clock(day, hour=10):
    aware = timezone.make_aware(datetime.combine(day, time(hour=hour)), timezone.get_current_timezone())
    return int(aware.timestamp())


class FakeZapi:
    """只实现巡检用到的三个方法：item_get / host_get / history_get。"""

    def __init__(self, items, history):
        self._items = items
        self._history = history

    async def item_get(self, **params):
        return self._items

    async def host_get(self, **params):
        return [ZAPIHost(hostid="1", host="SW-1", name="SW-1")]

    async def history_get(self, **params):
        wanted = set(params.get("itemids") or [])
        return [ZAPIHistory(itemid=itemid, clock=str(clock), value=str(value)) for itemid, clock, value in self._history if itemid in wanted]


def test_item_kind_hint_directions():
    assert inspection._item_kind_hint(_item("1", "net.if.in[ifHCInOctets.1]", "接口入向带宽")) == ("bps", "in")
    assert inspection._item_kind_hint(_item("2", "net.if.out[ifHCOutOctets.1]", "接口出向带宽")) == ("bps", "out")
    assert inspection._item_kind_hint(_item("3", "net.if.in[ifHCInOctets.1]", "入向带宽使用率")) == ("usage", "in")
    assert inspection._item_kind_hint(_item("4", "net.if.out[ifHCOutOctets.1]", "出向带宽使用率")) == ("usage", "out")
    assert inspection._item_kind_hint(_item("5", "ifSpeed", "接口速率")) == (None, None)


def test_collect_devices_aggregates_by_day():
    today = timezone.localdate()
    clock = _clock(today)
    cpu = _item("cpu-1", "cpu.util", "CPU 使用率")
    mem = _item("mem-1", "memory.util", "内存使用率")

    async def fake_items(group=None, *, key_=None, **filters):
        return [cpu] if key_ == inspection.CPU_KEYS else [mem] if key_ == inspection.MEM_KEYS else []

    zapi = FakeZapi([], [("cpu-1", clock, 10.0), ("cpu-1", clock + 60, 30.0), ("mem-1", clock, 40.0)])
    with (
        patch.object(queries, "items", new=AsyncMock(side_effect=fake_items)),
        patch.object(inspection, "get_zapi", new=AsyncMock(return_value=zapi)),
    ):
        payload = asyncio.run(inspection.collect(today.isoformat(), today.isoformat(), []))

    assert payload["run"]["status"] == "success"
    assert len(payload["devices"]) == 1
    row = payload["devices"][0]
    assert row["date"] == today.isoformat()
    assert row["cpu_avg"] == 20.0
    assert row["cpu_max"] == 30.0
    assert row["memory_avg"] == 40.0
    assert payload["interfaces"] == []


def test_collect_devices_respects_host_list_and_window():
    today = timezone.localdate()
    inside = _clock(today, hour=5)
    outside = _clock(today, hour=12)
    cpu = _item("cpu-1", "cpu.util", "CPU 使用率")
    mem = _item("mem-1", "memory.util", "内存使用率")

    async def fake_items(group=None, *, key_=None, **filters):
        return [cpu] if key_ == inspection.CPU_KEYS else [mem] if key_ == inspection.MEM_KEYS else []

    zapi = FakeZapi([], [("cpu-1", inside, 10.0), ("cpu-1", outside, 30.0), ("mem-1", inside, 40.0)])
    with (
        patch.object(queries, "items", new=AsyncMock(side_effect=fake_items)),
        patch.object(inspection, "get_zapi", new=AsyncMock(return_value=zapi)),
    ):
        payload = asyncio.run(
            inspection.collect(
                today.isoformat(),
                today.isoformat(),
                [],
                device_hosts=["SW-1"],
                window_start="00:00:00",
                window_end="06:00:00",
            )
        )
        empty = asyncio.run(
            inspection.collect(
                today.isoformat(),
                today.isoformat(),
                [],
                device_hosts=["OTHER"],
                window_start="00:00:00",
                window_end="06:00:00",
            )
        )

    assert payload["devices"][0]["cpu_avg"] == 10.0
    assert payload["devices"][0]["cpu_max"] == 10.0
    assert empty["devices"] == []


def test_collect_interfaces_splits_direction_and_kind():
    today = timezone.localdate()
    clock = _clock(today)
    items = [
        _item("in-bps", "net.if.in[ifHCInOctets.1]", "接口入向带宽"),
        _item("out-bps", "net.if.out[ifHCOutOctets.1]", "接口出向带宽"),
        _item("in-usage", "net.if.in[ifHCInOctets.1]", "入向带宽使用率"),
        _item("out-usage", "net.if.out[ifHCOutOctets.1]", "出向带宽使用率"),
    ]
    history = [
        ("in-bps", clock, 100.0),
        ("in-bps", clock + 60, 300.0),
        ("out-bps", clock, 500.0),
        ("in-usage", clock, 10.0),
        ("out-usage", clock, 20.0),
    ]
    zapi = FakeZapi(items, history)
    targets = [{"host": "SW-1", "ifname": "GE1/0/1", "itemids": ["in-bps", "out-bps", "in-usage", "out-usage"]}]

    with patch.object(inspection, "get_zapi", new=AsyncMock(return_value=zapi)):
        payload = asyncio.run(inspection.collect(today.isoformat(), today.isoformat(), targets))

    assert len(payload["interfaces"]) == 1
    row = payload["interfaces"][0]
    assert row["host"] == "SW-1"
    assert row["ifname"] == "GE1/0/1"
    assert row["in_bps_avg"] == 200.0
    assert row["in_bps_max"] == 300.0
    assert row["out_bps_max"] == 500.0
    assert row["in_usage_avg"] == 10.0
    assert row["out_usage_avg"] == 20.0


def test_collect_rejects_reversed_range():
    with pytest.raises(ValueError, match="date_start 不能晚于 date_end"):
        asyncio.run(inspection.collect("2026-11-25", "2026-11-24", []))


def test_collect_defaults_to_yesterday():
    today = timezone.localdate()

    async def empty_items(group=None, *, key_=None, **filters):
        return []

    zapi = FakeZapi([], [])
    with (
        patch.object(queries, "items", new=AsyncMock(side_effect=empty_items)),
        patch.object(inspection, "get_zapi", new=AsyncMock(return_value=zapi)),
    ):
        payload = asyncio.run(inspection.collect())

    assert payload["date_end"] == (today - timedelta(days=1)).isoformat()
    assert payload["date_start"] == payload["date_end"]
