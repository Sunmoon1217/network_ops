"""链路带宽直取 Zabbix → Redis 缓存（**不落库**）。

只做链路：设备状态与 Autotask 工单 / SLB / 巡检仍走原来的
``collect_dashboard → write_dashboard`` 落库链。这里是另一条只读链：

    conf/links.json → queries.link_history（并发）→ 3 分钟分桶 → SET dashboard:link:series

缓存 value 是「完整窗口结果 + 脱敏展示字段」，同步的读接口只 ``GET`` 这一个 key，
所以不存在读放大，也不需要处理同步 / 异步混用。Zabbix 抖动时保留上一份缓存
（TTL 大于刷新周期）；全部链路失败抛 :class:`LinkCollectionError`——管理命令非零退出，
Celery 任务捕获它只记一条 ERROR 并返回 ``status=failed``（不 raise，避免 180s 一轮刷屏）。
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from functools import lru_cache
from logging import getLogger
from typing import Any

import redis
from django.conf import settings
from django.utils import timezone

from .link_config import LinkConfig, LinkTarget, load_links_config
from .zabbix import queries

logger = getLogger(__name__)

# 采样按 3 分钟对齐（与旧采集器 _aligned_now 的口径一致）
BUCKET_SECONDS = 180


class LinkCollectionError(RuntimeError):
    """全部链路采集失败（一条都没成）。

    继承 ``RuntimeError`` 保持既有调用方（管理命令的 ``except Exception``）不用改；
    单独成类是为了让 worker 日志里能一眼分辨「外部数据源整体不可用」与真正的编码错误。
    """


def _redis_client():
    return redis.from_url(settings.REDIS_URL, socket_timeout=10, socket_connect_timeout=5)


def _bucket(clock: int) -> int:
    return clock - clock % BUCKET_SECONDS


def _time_label(clock: int) -> str:
    """unix clock → 本地时区 ``HH:MM``（与旧 _linechart_rows 的时间轴一致）。"""
    return timezone.localtime(datetime.fromtimestamp(clock, tz=UTC)).strftime("%H:%M")


async def build_link_payload(
    config: LinkConfig,
    *,
    window_hours: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """并发取所有启用链路的历史样本，按 3 分钟桶聚合，返回可 JSON 序列化的完整结果。"""
    hours = window_hours or settings.DASHBOARD_LINK_WINDOW_HOURS
    current = now or timezone.now()
    end = int(current.timestamp())
    start = end - hours * 3600

    enabled = config.enabled_targets()
    results = await asyncio.gather(
        *(queries.link_history(target.host, target.ifname, time_from=start, time_till=end) for target in enabled),
        return_exceptions=True,
    )

    # bucket → scope → subject → 该桶内多监控项的 max（与旧 link_peak 的取 max 口径一致）
    buckets: dict[int, dict[str, dict[str, float]]] = {}
    failures: list[tuple[LinkTarget, BaseException]] = []
    for target, result in zip(enabled, results, strict=True):
        if isinstance(result, BaseException):
            failures.append((target, result))
            continue
        for clock, value in result:
            if clock < start or clock > end:
                continue
            scope_data = buckets.setdefault(_bucket(clock), {}).setdefault(target.scope, {})
            previous = scope_data.get(target.subject)
            scope_data[target.subject] = value if previous is None else max(previous, value)

    # 全部失败才抛；单条失败只 warning（其余线路照常显示）。
    # 全挂时**不再逐条 warning**：异常消息里已带每个 target 的原因；``from None`` 去掉
    # asyncio 的异常链。管理命令照旧非零退出，Celery 任务捕获它只记一条 ERROR、返回
    # status=failed（不 raise，避免 180s 一轮刷屏），下个周期自动重试。
    if enabled and len(failures) == len(enabled):
        detail = "; ".join(f"{target.scope}/{target.subject}: {type(exc).__name__}: {exc}" for target, exc in failures)
        raise LinkCollectionError(f"全部 {len(failures)} 条链路采集失败 —— {detail}") from None

    for target, exc in failures:
        logger.warning("链路历史采集失败: %s/%s, err=%s", target.scope, target.subject, exc)

    return {
        **config.meta(),
        "window_hours": hours,
        "refreshed_at": current.isoformat(),
        "points": [{"time": _time_label(bucket), "data": buckets[bucket]} for bucket in sorted(buckets)],
    }


def refresh_link_cache(config: LinkConfig | None = None, *, client=None) -> dict[str, Any]:
    """同步入口：采集 → ``SET dashboard:link:series``（带 TTL），返回写入摘要。

    Celery 任务、管理命令、beat 启动钩子共用这一个函数，避免三处逻辑分叉。
    全部链路失败时抛 :class:`LinkCollectionError`（不写缓存，旧值靠 TTL 继续服务）。
    """
    config = config or load_links_config()
    payload = asyncio.run(build_link_payload(config))
    raw = json.dumps(payload, ensure_ascii=False)
    (client or _redis_client()).set(settings.DASHBOARD_LINK_CACHE_KEY, raw, ex=settings.DASHBOARD_LINK_CACHE_TTL)
    summary = {
        "points": len(payload["points"]),
        "targets": len(payload["targets"]),
        "refreshed_at": payload["refreshed_at"],
    }
    logger.info("链路缓存已刷新: %s", summary)
    return summary


def read_link_cache(*, client=None) -> dict[str, Any] | None:
    """读缓存；Redis 不可用或内容损坏时返回 None（调用方降级为空结果，不抛到请求里）。"""
    try:
        raw = (client or _redis_client()).get(settings.DASHBOARD_LINK_CACHE_KEY)
    except redis.RedisError as exc:
        logger.warning("链路缓存读取失败: %s", exc)
        return None
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        logger.warning("链路缓存内容不是合法 JSON")
        return None
    return payload if isinstance(payload, dict) else None


@lru_cache(maxsize=1)
def _static_link_meta() -> dict[str, Any]:
    """展示字段随版本走、不依赖 Zabbix：缓存起来避免每个大屏请求都读文件 + 校验。"""
    return load_links_config().meta()


def empty_link_payload() -> dict[str, Any]:
    """缓存未生成时的空壳：只带静态 meta，**不造任何数值点**。

    读接口用它保证前端永远拿得到 panels / scopes / targets，冷启动时能画出空图框；
    ``refreshed_at=None`` 表示「还没采到过」，前端据此提示数据未更新。
    """
    return {**_static_link_meta(), "points": [], "refreshed_at": None}
