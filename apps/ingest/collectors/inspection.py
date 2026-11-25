"""巡检采集：从 Zabbix 取指定日期区间、指定每日时段的 CPU / 内存 / 接口带宽，按天聚合。

设备侧只采 ``device_hosts`` 清单内主机（``None`` 表示不限），专线侧只采 ``targets``。
只调 Zabbix、返回可 JSON 序列化的 dict，**不碰数据库、不 import analysis**；写库由
``analysis.write_inspection`` 唯一负责。区间内按本地时区的自然日分桶，一天一行。
方向识别与字段口径见 handbook/analysis.md「巡检」。
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from logging import getLogger
from statistics import fmean
from typing import Any, TypedDict

from django.utils import timezone

from .dashboard import CPU_KEYS, DEVICE_GROUPS, MEM_KEYS
from .zabbix import get_zapi, queries

logger = getLogger(__name__)

# history.get 单次 batch 的监控项数：一天 288 点，20 项一批约 6k 行
HISTORY_BATCH = 20
# 每天按 288 点估算的 limit 余量（多核 CPU 等会放大，给 400）
LIMIT_PER_DAY = 400

_USAGE_HINTS = ("使用率", "利用率", "utilization", "util", "usage")
_BPS_HINTS = ("带宽", "流量", "octets", "bps", "bits", "ifin", "ifout")
_IGNORE_HINTS = ("speed", "速率", "状态", "status")

_OUT_TOKENS = ("net.if.out", "ifoutoctets", "ifhcoutoctets", ".out[", "_out[", "_out.")
_IN_TOKENS = ("net.if.in", "ifinoctets", "ifhcinoctets", ".in[", "_in[", "_in.")


class RunPayload(TypedDict):
    status: str
    device_count: int
    interface_count: int
    started_at: str
    finished_at: str
    error: str


class InspectionPayload(TypedDict):
    """跨任务契约：ingest 采集产出 → analysis 写库任务逐字段消费。"""

    date_start: str
    date_end: str
    devices: list[dict[str, Any]]
    interfaces: list[dict[str, Any]]
    run: RunPayload


def _parse_day(value: str | date | None, default: date) -> date:
    """接受 ``YYYY-MM-DD`` / ``date`` / 空；空则用 ``default``。"""
    if value is None:
        return default
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _day_start(day: date) -> datetime:
    """本地时区当天 00:00（aware）。"""
    return timezone.make_aware(datetime.combine(day, time.min), timezone.get_current_timezone())


def _parse_window(window_start: str | None, window_end: str | None) -> tuple[time, time] | None:
    """``HH:MM[:SS]`` → 当天的 ``[开始, 结束]``；任一为空则不限时段（整天）。"""
    if not window_start or not window_end:
        return None
    start = time.fromisoformat(window_start)
    end = time.fromisoformat(window_end)
    if start >= end:
        raise ValueError(f"巡检时间范围结束必须晚于开始: {start} >= {end}")
    return start, end


def _bounds(date_start: date, date_end: date, window: tuple[time, time] | None) -> tuple[int, int]:
    """区间 + 时段 → unix 秒 ``[start, end]``；未配置时段时取整段自然日。"""
    tz = timezone.get_current_timezone()
    if window is None:
        return int(_day_start(date_start).timestamp()), int(_day_start(date_end + timedelta(days=1)).timestamp())
    start_time, end_time = window
    start = int(timezone.make_aware(datetime.combine(date_start, start_time), tz).timestamp())
    # 结束时刻含当秒（TimeField 精度到秒），+1 后由 history_get 的 time_till 截断
    return start, int(timezone.make_aware(datetime.combine(date_end, end_time), tz).timestamp()) + 1


def _local_time(clock: int) -> datetime:
    """Zabbix clock（unix 秒）→ 本地时区的 datetime。"""
    return timezone.localtime(datetime.fromtimestamp(clock, tz=UTC))


def _in_window(moment: datetime, window: tuple[time, time] | None) -> bool:
    return window is None or window[0] <= moment.time() <= window[1]


def _as_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _agg(values: list[float]) -> tuple[float | None, float | None]:
    """样本 → ``(日均, 峰值)``；空样本给 ``(None, None)``，不用 0 伪装。"""
    if not values:
        return None, None
    return round(fmean(values), 2), round(max(values), 2)


def _item_kind_hint(item) -> tuple[str | None, str | None]:
    """按 key_ 与名称判定 ``(kind, direction)``：kind ∈ bps/usage，direction ∈ in/out。"""
    key = (item.key_ or "").lower()
    name = item.name or ""
    blob = f"{key} {name}".lower()
    if any(hint in blob for hint in _IGNORE_HINTS):
        return None, None
    if any(hint in blob for hint in _USAGE_HINTS):
        kind = "usage"
    elif any(hint in blob for hint in _BPS_HINTS):
        kind = "bps"
    else:
        return None, None

    direction = None
    if any(token in key for token in _OUT_TOKENS) or "出" in name or "发送" in name:
        direction = "out"
    elif any(token in key for token in _IN_TOKENS) or "入" in name or "接收" in name:
        direction = "in"
    return kind, direction


async def _history_values(itemids: list[str], start: int, end: int, days: int) -> dict[str, list[tuple[int, float]]]:
    """批量取监控项区间历史，返回 ``{itemid: [(clock, value)]}``；单批失败只 warning。"""
    if not itemids:
        return {}
    zapi = await get_zapi()
    batches = [itemids[index : index + HISTORY_BATCH] for index in range(0, len(itemids), HISTORY_BATCH)]
    results = await asyncio.gather(
        *(zapi.history_get(itemids=batch, history=0, time_from=start, time_till=end, limit=max(2000, LIMIT_PER_DAY * days)) for batch in batches),
        return_exceptions=True,
    )
    values: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for batch, result in zip(batches, results, strict=True):
        if isinstance(result, BaseException):
            logger.warning("巡检历史采集失败，items=%s: %s", batch[:3], result)
            continue
        for row in result:
            value = _as_float(row.value)
            if value is None:
                continue
            try:
                clock = int(row.clock)
            except (TypeError, ValueError):
                continue
            values[row.itemid].append((clock, value))
    return dict(values)


async def _device_item_meta() -> dict[str, dict[str, str]]:
    """``{itemid: {"host", "kind"}}``：按设备组并发查 CPU / 内存监控项。"""
    groups = list(DEVICE_GROUPS.items())
    results = await asyncio.gather(
        *(
            asyncio.gather(
                queries.items(group=group, key_=CPU_KEYS),
                queries.items(group=group, key_=MEM_KEYS),
                return_exceptions=True,
            )
            for _, group in groups
        ),
        return_exceptions=True,
    )
    meta: dict[str, dict[str, str]] = {}
    for (_slug, group), pair in zip(groups, results, strict=True):
        if isinstance(pair, BaseException):
            logger.warning("巡检设备组监控项查询失败: %s, err=%s", group, pair)
            continue
        for kind, batch in zip(("cpu", "mem"), pair, strict=True):
            if isinstance(batch, BaseException):
                logger.warning("巡检 %s 监控项查询失败: %s, err=%s", kind, group, batch)
                continue
            for item in batch:
                host = (item.hosts[0].name or item.hosts[0].host) if item.hosts else None
                if host:
                    meta[item.itemid] = {"host": host, "kind": kind}
    return meta


async def _collect_devices(
    days: set[date],
    start: int,
    end: int,
    device_hosts: list[str] | None = None,
    window: tuple[time, time] | None = None,
) -> list[dict[str, Any]]:
    """设备 CPU / 内存：区间样本按 (日期, 主机) 分桶后聚合。

    ``device_hosts`` 为 ``None`` 时不限主机（兼容旧调用），否则只保留清单内主机；
    空清单表示没有配置设备巡检对象，直接返回空。
    """
    meta = await _device_item_meta()
    if device_hosts is not None:
        allowed = set(device_hosts)
        meta = {itemid: info for itemid, info in meta.items() if info["host"] in allowed}
    if not meta:
        return []
    histories = await _history_values(sorted(meta), start, end, max(1, len(days)))
    buckets: dict[tuple[date, str], dict[str, list[float]]] = defaultdict(lambda: {"cpu": [], "mem": []})
    for itemid, samples in histories.items():
        info = meta.get(itemid)
        if info is None:
            continue
        for clock, value in samples:
            moment = _local_time(clock)
            if moment.date() in days and _in_window(moment, window):
                buckets[(moment.date(), info["host"])][info["kind"]].append(value)

    rows: list[dict[str, Any]] = []
    for (day, host), data in sorted(buckets.items()):
        cpu_avg, cpu_max = _agg(data["cpu"])
        mem_avg, mem_max = _agg(data["mem"])
        if cpu_avg is None and mem_avg is None:
            continue
        rows.append(
            {
                "date": day.isoformat(),
                "host": host,
                "cpu_avg": cpu_avg,
                "cpu_max": cpu_max,
                "memory_avg": mem_avg,
                "memory_max": mem_max,
                "payload": {"cpu_samples": len(data["cpu"]), "mem_samples": len(data["mem"])},
            }
        )
    return rows


async def _target_items(target: dict[str, Any]) -> list[Any]:
    """一个接口目标的带宽类监控项：给了 itemids 按 ID 查，否则按主机 + 接口名搜。"""
    zapi = await get_zapi()
    if target.get("itemids"):
        return await zapi.item_get(itemids=target["itemids"])
    hosts = await zapi.host_get(search={"name": target["host"]}, output=["hostid"])
    if not hosts:
        return []
    return await zapi.item_get(hostids=[hosts[0].hostid], search={"name": target["ifname"]})


async def _interface_item_meta(targets: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """``{itemid: {"host","ifname","kind","direction"}}``；单目标失败只 warning。"""
    results = await asyncio.gather(*(_target_items(target) for target in targets), return_exceptions=True)
    meta: dict[str, dict[str, Any]] = {}
    for target, result in zip(targets, results, strict=True):
        if isinstance(result, BaseException):
            logger.warning("巡检接口监控项查询失败: %s@%s, err=%s", target["host"], target["ifname"], result)
            continue
        for item in result:
            kind, direction = _item_kind_hint(item)
            if kind is None:
                continue
            meta[item.itemid] = {
                "host": target["host"],
                "ifname": target["ifname"],
                "kind": kind,
                "direction": direction,
                "name": item.name or item.itemid,
            }
    return meta


async def _collect_interfaces(
    days: set[date],
    start: int,
    end: int,
    targets: list[dict[str, Any]],
    window: tuple[time, time] | None = None,
) -> list[dict[str, Any]]:
    """接口带宽：入/出方向各聚合 bps 与使用率的日均、峰值。"""
    if not targets:
        return []
    meta = await _interface_item_meta(targets)
    if not meta:
        return []
    histories = await _history_values(sorted(meta), start, end, max(1, len(days)))
    buckets: dict[tuple[date, str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for itemid, samples in histories.items():
        info = meta.get(itemid)
        if info is None or info["direction"] is None:
            continue
        key = f"{info['direction']}_{info['kind']}"
        for clock, value in samples:
            moment = _local_time(clock)
            if moment.date() in days and _in_window(moment, window):
                buckets[(moment.date(), info["host"], info["ifname"])][key].append(value)

    rows: list[dict[str, Any]] = []
    for (day, host, ifname), data in sorted(buckets.items()):
        row: dict[str, Any] = {"date": day.isoformat(), "host": host, "ifname": ifname}
        for key in ("in_bps", "out_bps", "in_usage", "out_usage"):
            avg, peak = _agg(data.get(key, []))
            row[f"{key}_avg"] = avg
            row[f"{key}_max"] = peak
        if all(row[f"{key}_{suffix}"] is None for key in ("in_bps", "out_bps", "in_usage", "out_usage") for suffix in ("avg", "max")):
            continue
        row["payload"] = {
            "items": [
                {"itemid": itemid, "name": info["name"], "kind": info["kind"], "direction": info["direction"]}
                for itemid, info in meta.items()
                if info["host"] == host and info["ifname"] == ifname
            ]
        }
        rows.append(row)
    return rows


async def collect(
    date_start: str | None = None,
    date_end: str | None = None,
    targets: list[dict[str, Any]] | None = None,
    device_hosts: list[str] | None = None,
    window_start: str | None = None,
    window_end: str | None = None,
) -> InspectionPayload:
    """采集区间内的巡检指标 → 纯 dict；日期缺省为「昨天」。

    ``window_start`` / ``window_end`` 为每天采集时段（``HH:MM[:SS]``），缺省整天；
    ``device_hosts`` 限定设备巡检对象，``None`` 表示不限（兼容旧调用）。
    单组 / 单接口失败只 warning 并跳过，全部失败的异常交给调用方记批次 ``failed``。
    """
    started = timezone.now()
    today = timezone.localdate()
    end_day = _parse_day(date_end, today - timedelta(days=1))
    start_day = _parse_day(date_start, end_day)
    if start_day > end_day:
        raise ValueError(f"date_start 不能晚于 date_end: {start_day} > {end_day}")

    days = {start_day + timedelta(days=offset) for offset in range((end_day - start_day).days + 1)}
    window = _parse_window(window_start, window_end)
    start, end = _bounds(start_day, end_day, window)

    devices, interfaces = await asyncio.gather(
        _collect_devices(days, start, end, device_hosts, window),
        _collect_interfaces(days, start, end, targets or [], window),
        return_exceptions=True,
    )
    error = ""
    if isinstance(devices, BaseException):
        logger.warning("巡检设备指标采集失败: %s", devices)
        error = f"设备指标: {devices}"
        devices = []
    if isinstance(interfaces, BaseException):
        logger.warning("巡检接口指标采集失败: %s", interfaces)
        error = f"{error}; 接口指标: {interfaces}".strip("; ")
        interfaces = []

    finished = timezone.now()
    return {
        "date_start": start_day.isoformat(),
        "date_end": end_day.isoformat(),
        "devices": devices,
        "interfaces": interfaces,
        "run": {
            "status": "failed" if error else "success",
            "device_count": len(devices),
            "interface_count": len(interfaces),
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "error": error,
        },
    }
