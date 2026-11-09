"""Dashboard 采集编排：**只采集，不落库、不 import analysis**。

Celery 同步任务 ``ingest.tasks.collect_dashboard`` 用 ``asyncio.run(collect(source))``
取回一份纯 dict payload（可 JSON 序列化），再按任务名投递给 analysis 的写库任务。
这里是采集器（ingest）的一部分；存储与读接口都在 analysis。

payload 形状（``analysis.tasks.write_dashboard`` 按此消费）::

    {
      "source": "zabbix" | "autotask",
      "batch_at": "<ISO8601>",
      "metrics": [{"panel","group","name","value","list_value","sampled_at"}],
      "samples": [{"kind","scope","subject","metric_key","value","payload","sampled_at"}],
      "cases":   [{"case_no","title","applicant","raw"}],
      "run":     {"status","item_count","started_at","finished_at","error"},
    }

``sampled_at`` 是数据源采样时刻（3 分钟对齐），与落库时刻 ``updated_at`` 分开。
单个组 / 单个接口失败只记 warning，其余数据照常返回；整批失败才写 ``run.status=failed``，
不让一次外部接口抖动清空整屏。
"""

import asyncio
from datetime import timedelta
from logging import getLogger
from typing import Any, TypedDict

from django.utils import timezone

from .autotask.autotask import fetch_case, fetch_inspect, fetch_slb
from .zabbix import queries

logger = getLogger(__name__)


class RunPayload(TypedDict):
    status: str
    item_count: int
    started_at: str
    finished_at: str
    error: str


class MetricPayload(TypedDict):
    panel: str
    group: str
    name: str
    value: Any
    list_value: list[Any]
    sampled_at: str


class SamplePayload(TypedDict):
    kind: str
    scope: str
    subject: str
    metric_key: str
    value: float | None
    payload: dict[str, Any]
    sampled_at: str


class CasePayload(TypedDict):
    case_no: str
    title: str
    applicant: str
    raw: dict[str, Any]


class DashboardPayload(TypedDict):
    """采集结果的跨任务契约：ingest 产出 → analysis 写库任务逐字段消费。

    显式成 TypedDict 而不是 ``dict[str, Any]``：调用方在两个分支给 payload 赋值时
    类型不会退化成「值的联合」，``payload["run"]["status"]`` 之类的索引才可校验。
    """

    source: str
    batch_at: str
    metrics: list[MetricPayload]
    samples: list[SamplePayload]
    cases: list[CasePayload]
    run: RunPayload


# Zabbix 主机组名按现场配置；slug 与前端 MidCard-1.vue 的 CARD_CONFIG 对齐。
DEVICE_GROUPS = {
    "switch": "Type:交换机",
    "router": "Type:路由器",
    "firewall": "Type:防火墙",
    "loadbalance": "Type:负载均衡",
    "dns": "Type:DNS",
}
CPU_KEYS = ["cpu.util", "cpu.utilization", "topsec.cpu", "cpu.usage"]
MEM_KEYS = ["memory.util", "mem.tmm.ratio", "zdns.mem.usage"]

# 链路采集目标从旧 link_dict 迁来：host 是现场值，**ifname 仍是占位**，填上真实接口名
# 之后才会拿到带宽数据（填之前 link_peak 找不到监控项，采样值为 null）。
# 放在 ingest 侧而不是 analysis.LinkTarget：采集器执行时不能反向读 analysis 的表。
LINK_TARGETS = (
    ("ipv4", "zjbgp", "ZGCB-ZJE04-INT-AS01", "ifname"),
    ("ipv4", "jxqcu", "ZGCB-JXQA03-INT-AS01", "ifname"),
    ("ipv4", "jxqct", "ZGCB-JXQA03-INT-AS01", "ifname"),
    ("ipv6", "zjbgp", "ZGCB-ZJE04-INT-AS01", "ifname"),
    ("ipv6", "jxqcu", "ZGCB-JXQA03-INT-AS01", "ifname"),
    ("ipv6", "jxqct", "ZGCB-JXQA03-INT-AS01", "ifname"),
    ("fwlink", "coreyw", "ZGCB-ZJB02-COREYW-FW01", "ifname"),
    ("fwlink", "intyw", "ZGCB-ZJB02-INTYW-FW01", "ifname"),
    ("fwlink", "mgtyw", "ZGCB-ZJB02-MGTYW-FW01", "ifname"),
    ("fwlink", "intdmz", "ZGCB-ZJE04-INT-FW01", "ifname"),
)


def _aligned_now():
    """对齐到最近的整 3 分钟（aware，别用 naive datetime.now()）。"""
    now = timezone.now().replace(second=0, microsecond=0)
    return now - timedelta(minutes=now.minute % 3)


def _iso(value):
    return value.isoformat()


def _metric(panel, group, name, *, value=None, list_value=None, sampled_at):
    return {
        "panel": panel,
        "group": group,
        "name": name,
        "value": value,
        "list_value": list_value or [],
        "sampled_at": _iso(sampled_at),
    }


def _sample(kind, scope, subject, value, *, metric_key="", payload=None, sampled_at):
    return {
        "kind": kind,
        "scope": scope,
        "subject": subject,
        "metric_key": metric_key,
        "value": value,
        "payload": payload or {},
        "sampled_at": _iso(sampled_at),
    }


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def _collect_group(slug, group_name, sampled_at):
    """一个设备组：数量 / 告警 / CPU / 内存；四类调用并发、失败彼此隔离。"""
    count, probs, cpu, mem = await asyncio.gather(
        queries.device_count(group_name),
        queries.problems(group_name),
        queries.items(group=group_name, key_=CPU_KEYS),
        queries.items(group=group_name, key_=MEM_KEYS),
        return_exceptions=True,
    )
    metrics, samples = [], []
    for label, result in (("设备数量", count), ("告警", probs), ("CPU", cpu), ("内存", mem)):
        if isinstance(result, BaseException):
            logger.warning("Zabbix %s 采集失败: group=%s, err=%s", label, group_name, result)

    if not isinstance(count, BaseException):
        metrics.append(_metric("devicestatus", slug, "count", value=count, sampled_at=sampled_at))
    if not isinstance(probs, BaseException):
        metrics.append(_metric("devicestatus", slug, "problems", list_value=[row.model_dump() for row in probs], sampled_at=sampled_at))

    for label, kind, result in (("cpu", "device_cpu", cpu), ("mem", "device_mem", mem)):
        if isinstance(result, BaseException):
            continue
        top = []
        for item in result:
            host = (item.hosts[0].name or item.hosts[0].host) if item.hosts else item.itemid
            value = _as_float(item.lastvalue)
            samples.append(_sample(kind, slug, host, value, metric_key=item.key_ or item.itemid, sampled_at=sampled_at))
            top.append({"label": host, "value": value})
        top.sort(key=lambda row: row["value"] if row["value"] is not None else -1.0, reverse=True)
        top = top[:5]
        metrics.append(_metric("devicestatus", slug, f"{label}max", value=top[0]["value"] if top else None, sampled_at=sampled_at))
        metrics.append(_metric("devicestatus", slug, f"{label}top", list_value=top, sampled_at=sampled_at))

    return (count if not isinstance(count, BaseException) else 0), metrics, samples


async def _collect_links(sampled_at):
    """链路带宽峰值：一行一条链路一个采样点，供 API 聚合回 linechart 视图。"""
    if not LINK_TARGETS:
        return []
    results = await asyncio.gather(
        *(queries.link_peak(host=host, ifname=ifname) for _, _, host, ifname in LINK_TARGETS),
        return_exceptions=True,
    )
    samples = []
    for (group, name, _, _), result in zip(LINK_TARGETS, results, strict=True):
        if isinstance(result, BaseException):
            logger.warning("链路峰值采集失败: %s/%s, err=%s", group, name, result)
            peak, itemids = None, []
        else:
            peak, itemids = result["peak"], result["itemids"]
        samples.append(_sample("link_bandwidth", group, name, peak, payload={"itemids": itemids}, sampled_at=sampled_at))
    return samples


def _success_rate(case_rows):
    """真实成功率：外部字段带 status 才算，没有就返回 None（不写恒为 100 的假指标）。"""
    statuses = [row["raw"].get("status") for row in case_rows if row["raw"].get("status")]
    if not statuses:
        return None
    return round(100 * sum(status == "成功" for status in statuses) / len(statuses), 1)


async def _collect_autotask(sampled_at):
    """工单 / SLB / 巡检三个接口并发；工单保留外部原字段供前端表格用。"""
    cases, slb, inspect = await asyncio.gather(fetch_case(), fetch_slb(), fetch_inspect(), return_exceptions=True)
    metrics, case_rows = [], []

    if isinstance(cases, BaseException):
        logger.warning("工单采集失败: %s", cases)
    else:
        for case in cases:
            raw = case.model_dump()
            case_rows.append({"case_no": case.case_no, "title": case.title, "applicant": case.shenqing, "raw": raw})
        metrics.append(
            _metric("statusbar", "itsmtask", "count", list_value=[{"count": len(case_rows), "success": _success_rate(case_rows)}], sampled_at=sampled_at)
        )

    if isinstance(slb, BaseException):
        logger.warning("SLB 采集失败: %s", slb)
    else:
        # 前端要 {instance, listener}；旧 update_aliyunslb 错把巡检数据写进了这里。
        metrics.append(_metric("slb", "slb", "slb", list_value=[row.model_dump() for row in slb], sampled_at=sampled_at))

    if isinstance(inspect, BaseException):
        logger.warning("巡检采集失败: %s", inspect)
    else:
        metrics.append(_metric("inspection", "device", "list", list_value=[row.model_dump() for row in inspect], sampled_at=sampled_at))

    return metrics, case_rows


async def collect(source: str) -> DashboardPayload:
    """采集一个数据源 → 纯 payload（绝不碰数据库、绝不 import analysis）。"""
    started = timezone.now()
    sampled_at = _aligned_now()
    metrics, samples, cases, error = [], [], [], ""
    try:
        if source == "zabbix":
            grouped = await asyncio.gather(
                *(_collect_group(slug, group_name, sampled_at) for slug, group_name in DEVICE_GROUPS.items()),
                return_exceptions=True,
            )
            total = 0
            for (slug, _), result in zip(DEVICE_GROUPS.items(), grouped, strict=True):
                if isinstance(result, BaseException):
                    logger.warning("设备组采集失败: %s, err=%s", slug, result)
                    continue
                count, group_metrics, group_samples = result
                total += count
                metrics.extend(group_metrics)
                samples.extend(group_samples)
            metrics.append(_metric("statusbar", "devicecount", "count", list_value=[{"count": total}], sampled_at=sampled_at))
            samples.extend(await _collect_links(sampled_at))
        elif source == "autotask":
            metrics, cases = await _collect_autotask(sampled_at)
        else:
            raise ValueError(f"未知采集来源: {source}")
    except Exception as exc:
        error = str(exc)
        logger.exception("Dashboard 采集失败: source=%s", source)

    finished = timezone.now()
    return {
        "source": source,
        "batch_at": _iso(sampled_at),
        "metrics": metrics,
        "samples": samples,
        "cases": cases,
        "run": {
            "status": "failed" if error else "success",
            "item_count": len(metrics) + len(samples) + len(cases),
            "started_at": _iso(started),
            "finished_at": _iso(finished),
            "error": error,
        },
    }
