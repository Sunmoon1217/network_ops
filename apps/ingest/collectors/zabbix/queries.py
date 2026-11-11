"""Zabbix 查询编排层：**按业务意图**提供 4 个入口。

``zabbix.py`` 的 ``TypedZabbixAPI`` 只提供 ``<object>_get`` 扩展方法（一次官方 API
调用 + 有限参数固化 + response 校验实例化）；本层负责全部编排：范围解析、条件组合、
触发器关联、峰值计算。名称→ID、纯透传、单条详情这类实现细节都不是业务意图，
已收进私有助手，不对外暴露。

    device_count(...)   某主机组有多少台设备
    items(...)          查监控项当前值（可给 name / key_ 组合条件并发查）
    problems(...)       看当前告警（自动补齐触发器与主机）
    link_peak(...)      某主机某接口的带宽峰值（不给时间取当前值，给时间取区间峰值）
    link_history(...)   某主机某接口在区间内的历史样本（保留时间维度，供大屏分桶）

文件名不叫 ``tools.py``：与 ``apps/<域>/mcp/tools.py``（MCP 工具注册）语义不同；
未来 Zabbix 的 MCP 工具按约定住 ``apps/ingest/mcp/tools.py``，工具名以 ``zabbix_`` 开头。
"""

from asyncio import gather
from itertools import product
from logging import getLogger
from typing import Any, TypedDict

from .schemas import ZAPIHost, ZAPIItem, ZAPIProblem, ZAPITrigger
from .zabbix import get_zapi

logger = getLogger(__name__)


class LinkPeak(TypedDict):
    """链路带宽峰值结果。"""

    peak: float | None  # 无可用数值时为 None，不抛异常
    current: list[str | None]  # 各监控项的当前值
    itemids: list[str]  # 参与计算的监控项ID，便于溯源


async def _resolve_scope(
    group: str | None = None,
    groupids: list[str] | None = None,
    host: str | None = None,
    hostids: list[str] | None = None,
) -> dict[str, list[str]]:
    """把「名称或 ID」解析成官方 API 的过滤参数；主机组优先于主机。

    解析不到返回 ``{}``，**绝不返回空 ID 列表**：空 ``groupids`` / ``hostids`` 在
    Zabbix 里可能等于不过滤，会把一次范围查询变成全量查询。
    """
    ids = groupids or []
    if not ids and group:
        zapi = await get_zapi()
        groups = await zapi.hostgroup_get(search={"name": group}, output=["groupid"])
        ids = [row.groupid for row in groups]
    if ids:
        return {"groupids": ids}

    hosts = hostids or []
    if not hosts and host:
        zapi = await get_zapi()
        rows = await zapi.host_get(search={"name": host}, output=["hostid"])
        hosts = [row.hostid for row in rows]
    if hosts:
        return {"hostids": hosts}
    return {}


def _search_combinations(name: list[list[str]] | None, key_: list[str] | None) -> list[dict[str, Any]]:
    """把 name / key_ 两组条件做笛卡尔积，生成 ``item.get`` 的 search 条件列表。

    ``name`` 的每个元素本身是一组名称（Zabbix search 的 OR 列表），``key_`` 的每个
    元素是单个 key；两组都为空时必须拒绝，否则 ``search={}`` 会拉全量监控项。
    """
    groups: list[list[tuple[str, Any]]] = []
    if name:
        groups.append([("name", value) for value in name])
    if key_:
        groups.append([("key_", value) for value in key_])
    if not groups:
        raise ValueError("缺少监控项名称或者 key_")
    return [dict(combo) for combo in product(*groups)]


async def _trigger_map(triggerids: list[str]) -> dict[str, tuple[ZAPITrigger, ZAPIHost | None]]:
    """一次批量取触发器，按 triggerid 建映射；无关联主机时 host 为 None。"""
    zapi = await get_zapi()
    triggers = await zapi.trigger_get(triggerids=triggerids)
    # hosts 已在 schemas 声明为 list[ZAPIHost]，pydantic 完成嵌套实例化
    return {trigger.triggerid: (trigger, trigger.hosts[0] if trigger.hosts else None) for trigger in triggers}


async def _link_items(host: str, ifname: str, itemids: list[str] | None) -> list[ZAPIItem]:
    """链路带宽类监控项：给了 itemids 就按 ID 查，否则按主机名 + 接口名 / 带宽使用率搜。"""
    zapi = await get_zapi()
    if itemids:
        return await zapi.item_get(itemids=itemids)
    hostids = [row.hostid for row in await zapi.host_get(search={"name": host}, output=["hostid"])]
    if not hostids:
        return []
    return await zapi.item_get(hostids=hostids, search={"name": [ifname, "带宽使用率"]})


def _as_float(value: str | None) -> float | None:
    """Zabbix 的 lastvalue / value 是字符串，可能是小数或非数值；解析不了记 warning 并跳过。"""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        logger.warning("监控项数值无法解析: %r", value)
        return None


async def device_count(group: str | None = None, *, groupids: list[str] | None = None) -> int:
    """按主机组统计设备总数。

    无组条件 / 组名未匹配到时返回 0；API 调用失败则抛异常，不把故障伪装成「0 台设备」。
    """
    ids = (await _resolve_scope(group=group, groupids=groupids)).get("groupids", [])
    if not ids:
        logger.warning("未提供主机组或组名未匹配到，设备总数按 0 处理")
        return 0
    zapi = await get_zapi()
    # countOutput 返回标量（Zabbix 5+ 是字符串），不是对象列表，直接走官方动态 API
    return int(await zapi.host.get(groupids=ids, countOutput=1))


async def items(
    group: str | None = None,
    *,
    groupids: list[str] | None = None,
    name: list[list[str]] | None = None,
    key_: list[str] | None = None,
    **filters: Any,
) -> list[ZAPIItem]:
    """查监控项当前值；给了 ``name`` / ``key_`` 时按笛卡尔积并发出多组条件。

    ``group`` / ``groupids`` 限定主机组，其余官方参数（``hostids`` / ``itemids`` /
    ``search`` / ``limit`` ...）走 ``**filters`` 透传。单组失败记 warning 后跳过，
    其余结果照常返回；没有任何过滤条件时拒绝，避免拉全量监控项。
    """
    scope = await _resolve_scope(group=group, groupids=groupids)
    params: dict[str, Any] = {**filters, **scope}
    searches = _search_combinations(name, key_) if (name or key_) else []
    if not params and not searches:
        raise ValueError("查监控项需提供过滤条件（主机组 / 主机 / 监控项 / search），避免全量拉取")

    zapi = await get_zapi()
    if not searches:
        return await zapi.item_get(**params)

    results = await gather(
        *(zapi.item_get(**{**params, "search": search}) for search in searches),
        return_exceptions=True,
    )
    collected: list[ZAPIItem] = []
    for search, batch in zip(searches, results, strict=True):
        if isinstance(batch, BaseException):
            logger.warning("监控项查询失败，search=%s: %s", search, batch)
            continue
        collected.extend(batch)
    return collected


async def problems(
    group: str | None = None,
    *,
    groupids: list[str] | None = None,
    host: str | None = None,
    hostids: list[str] | None = None,
    limit: int | None = None,
) -> list[ZAPIProblem]:
    """取当前问题（触发器类），并**一次性**补齐各自的触发器与主机。

    主机组优先于主机；四者皆空或名称解析不到时抛 ``ValueError``，避免空
    ``groupids`` / ``hostids`` 导致全量查询。取不到触发器的问题仍保留，字段为 None。
    """
    params: dict[str, Any] = dict(await _resolve_scope(group=group, groupids=groupids, host=host, hostids=hostids))
    if not params:
        raise ValueError("需提供主机组或主机（名称或ID），无法获取问题列表")
    if limit is not None:
        params["limit"] = limit

    zapi = await get_zapi()
    rows = await zapi.problem_get(**params)
    triggers = await _trigger_map(sorted({row.objectid for row in rows})) if rows else {}

    resolved: list[ZAPIProblem] = []
    for row in rows:
        pair = triggers.get(row.objectid)
        trigger, problem_host = pair if pair is not None else (None, None)
        if pair is None:
            logger.warning("问题 %s 未匹配到触发器 %s", row.eventid, row.objectid)
        resolved.append(row.model_copy(update={"trigger": trigger, "host": problem_host}))
    return resolved


async def link_peak(
    host: str,
    ifname: str,
    *,
    itemids: list[str] | None = None,
    time_from: int | None = None,
    time_till: int | None = None,
    history_type: int = 0,
    limit: int = 180,
) -> LinkPeak:
    """取某主机某接口的带宽类监控项峰值。

    不给 ``time_from`` / ``time_till`` → 用各监控项 ``lastvalue`` 算当前峰值；
    给了（单边或成对）→ 走 ``history.get`` 算区间峰值。两种口径共用同一套
    「找监控项 → 解析数值 → 取最大值」，峰值统一为 ``float | None``；无可用
    数值时 ``peak=None`` 不抛异常，只有找不到监控项这类明确错误才抛 ``ValueError``。
    """
    monitored = await _link_items(host, ifname, itemids)
    if not monitored:
        raise ValueError(f"未找到监控项: {host}, {ifname}")

    if time_from is None and time_till is None:
        raw_values: list[str | None] = [item.lastvalue for item in monitored]
    else:
        params: dict[str, Any] = {
            "itemids": [item.itemid for item in monitored],
            "history": history_type,
            "limit": limit,
        }
        if time_from is not None:
            params["time_from"] = time_from
        if time_till is not None:
            params["time_till"] = time_till
        zapi = await get_zapi()
        histories = await zapi.history_get(**params)
        raw_values = [row.value for row in histories]

    values = [value for value in (_as_float(raw) for raw in raw_values) if value is not None]
    return LinkPeak(
        peak=round(max(values), 2) if values else None,
        current=[item.lastvalue for item in monitored],
        itemids=[item.itemid for item in monitored],
    )


async def link_history(
    host: str,
    ifname: str,
    *,
    time_from: int,
    time_till: int,
    history_type: int = 0,
    limit: int = 600,
) -> list[tuple[int, float]]:
    """某主机某接口在区间内的历史样本 ``[(clock, value)]``，保留时间维度。

    与 :func:`link_peak` 共用「找监控项」逻辑；一个 target 可能命中多个监控项
    （进出方向 / 带宽使用率），全部样本一起返回，由调用方按 3 分钟桶取 max。
    ``limit`` 按单 target 给足（3 小时 ≈ 60 个采样点 × 多个 item）。
    """
    monitored = await _link_items(host, ifname, None)
    if not monitored:
        raise ValueError(f"未找到监控项: {host}, {ifname}")
    zapi = await get_zapi()
    rows = await zapi.history_get(
        itemids=[item.itemid for item in monitored],
        history=history_type,
        time_from=time_from,
        time_till=time_till,
        limit=limit,
    )
    samples: list[tuple[int, float]] = []
    for row in rows:
        value = _as_float(row.value)
        if value is None:
            continue
        try:
            clock = int(row.clock)
        except (TypeError, ValueError):
            continue
        samples.append((clock, value))
    return samples
