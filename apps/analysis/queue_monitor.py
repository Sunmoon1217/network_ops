"""队列积压巡检：Celery 队列 + 访问流 Stream + 消费者心跳的只读监控。

为什么需要它：访问流链路是「celery 队列 → Redis Stream → 单写者 consumer」三段接力，
任何一段卡死（worker 挂了 / consumer OOM 循环 / 毒消息反复重投）都表现为**静默积压**——
2026-10 的实盘事故就是 Stream 里 47 条消息无人消化、consumer 反复 OOM 重启，而外部
没有任何信号。本模块把三段的关键指标一次性采出来，供三个出口共用：

- ``manage.py queue_status``：人看表格 / ``--json`` 机器可读，超阈值退出码 1（可接 cron 告警）；
- ``/api/analysis/queue-status/``：前端 Home 页的积压监控卡片轮询；
- 生产者背压：``access_stream.backlog()``（那是独立函数，本模块只读不干预）。

采集全部是 O(1) 的 Redis 命令（LLEN / HLEN / XLEN / XINFO GROUPS / XPENDING 明细
限量 50 条 / GET），不碰 worker、不碰数据库，轮询频率 30s 也无压力。

指标口径（别改坏）：

- ``queues``：celery 各队列的 LLEN——**排队未执行**的任务数；
- ``unacked``：``unacked`` hash 的 HLEN——已取走未确认的**执行中**任务数（worker
  死掉会滞留，是 worker 故障的先行指标）；
- ``stream.lag``：XINFO GROUPS 的 ``lag``——**从未投递给消费者**的积压（真实待消费量；
  XLEN 含已 ack 未 trim 的条目，不能当积压用，见 ``access_stream.backlog`` 的同款修正）；
- ``stream.pending``：PEL 条数——已投递未确认（含正在处理的 + 卡住的）；
- ``stream.top_pending``：按重投次数排序的前 5 条——``deliveries`` 高就是毒消息
  （consumer 反复失败不 ack、XAUTOCLAIM 反复捞回的形态）；
- ``heartbeat_age``：``access_flow:heartbeat`` 距今秒数——consumer 活性的唯一外部信号。

Redis 不可达时**不抛异常**：返回 ``redis_ok=False`` + critical 告警——监控自身炸掉
比被监控对象炸掉更没意义。
"""

from __future__ import annotations

import time
from logging import getLogger

from django.conf import settings

from analysis.access_stream import GROUP, HEARTBEAT_KEY, STREAM, get_redis

logger = getLogger(__name__)

#: 告警阈值默认值（命令行 ``queue_status`` 与 API 都以它为基准；只报警，不干预生产者）
DEFAULT_THRESHOLDS: dict[str, int] = {
    "max_queue": 1000,  # 单个 celery 队列长度（排队未执行）
    "max_unacked": 100,  # 执行中未确认任务数
    "max_stream_lag": 200,  # Stream 未投递积压
    "max_pending": 50,  # PEL 待确认（消费者卡死 / 反复失败的先行指标）
    "max_deliveries": 10,  # 单条消息重投次数（≥ 即判毒消息）
    "heartbeat_stale": 600,  # 心跳过期秒数（beat 每轮 ~5s 盖章，TTL 300s）
}

#: XPENDING 明细最多取多少条（按重投次数排序后再截前 5，避免大 PEL 拖垮采集）
_PENDING_PROBE = 50


def _queue_names() -> list[str]:
    """要巡检的 celery 队列名：默认队列 + CELERY_TASK_ROUTES 里声明的全部队列。"""
    names = {"celery"}
    for route in settings.CELERY_TASK_ROUTES.values():
        queue = route.get("queue")
        if queue:
            names.add(queue)
    return sorted(names)


def _stream_stats(client) -> dict:
    """访问流 Stream 的积压画像；键不存在（从未投递）按全零处理。"""
    info: dict = {"xlen": 0, "lag": None, "pending": 0, "consumers": 0, "top_pending": []}
    try:
        info["xlen"] = int(client.xlen(STREAM))
    except Exception:
        logger.warning("XLEN %s 读取失败", STREAM, exc_info=True)
    try:
        groups = client.xinfo_groups(STREAM)
    except Exception:
        # 键不存在（XINFO 对缺失键报错）或旧版 redis：按无组处理
        groups = []
    for group in groups or []:
        if group.get("name") != GROUP:
            continue
        info["pending"] = int(group.get("pending") or 0)
        info["consumers"] = int(group.get("consumers") or 0)
        lag = group.get("lag")
        info["lag"] = int(lag) if lag is not None else None
    if info["pending"]:
        try:
            entries = client.xpending_range(STREAM, GROUP, min="-", max="+", count=_PENDING_PROBE) or []
            top = sorted(entries, key=lambda e: int(e.get("times_delivered") or 0), reverse=True)[:5]
            info["top_pending"] = [
                {
                    "id": str(e.get("message_id")),
                    "idle_ms": int(e.get("time_since_delivered") or 0),
                    "deliveries": int(e.get("times_delivered") or 0),
                }
                for e in top
            ]
        except Exception:
            logger.warning("XPENDING 明细读取失败（忽略）", exc_info=True)
    return info


def _heartbeat_age(client) -> float | None:
    """消费者心跳距今秒数；键不存在（从未启动 / 已死超 TTL）返回 None。"""
    raw = client.get(HEARTBEAT_KEY)
    if raw is None:
        return None
    try:
        stamped = float(raw.decode() if isinstance(raw, bytes) else raw)
    except (TypeError, ValueError):
        return None
    return max(0.0, time.time() - stamped)


def collect(client=None, thresholds: dict | None = None) -> dict:
    """采集一轮队列积压全貌（只读），附上按阈值得出的告警列表。"""
    client = client or get_redis()
    stats: dict = {
        "checked_at": time.time(),
        "redis_ok": True,
        "error": None,
        "queues": {},
        "unacked": 0,
        "stream": None,
        "heartbeat_age": None,
        "thresholds": {**DEFAULT_THRESHOLDS, **(thresholds or {})},
    }
    try:
        stats["queues"] = {name: int(client.llen(name)) for name in _queue_names()}
        stats["unacked"] = int(client.hlen("unacked"))
        stats["stream"] = _stream_stats(client)
        stats["heartbeat_age"] = _heartbeat_age(client)
    except Exception as exc:
        logger.warning("队列巡检读取 Redis 失败", exc_info=True)
        stats["redis_ok"] = False
        stats["error"] = str(exc)
    stats["alerts"] = evaluate(stats)
    return stats


def evaluate(stats: dict, thresholds: dict | None = None) -> list[dict]:
    """按阈值把 stats 翻译成告警列表（warning / critical）；Redis 不可达是唯一的 critical 短路。"""
    t = {**DEFAULT_THRESHOLDS, **(thresholds or stats.get("thresholds") or {})}
    alerts: list[dict] = []

    def add(level: str, code: str, message: str) -> None:
        alerts.append({"level": level, "code": code, "message": message})

    if not stats.get("redis_ok"):
        add("critical", "redis_unreachable", f"Redis 不可达，队列状态未知: {stats.get('error')}")
        return alerts

    for name, length in (stats.get("queues") or {}).items():
        if length > t["max_queue"]:
            add("warning", "queue_backlog", f"celery 队列 {name} 积压 {length} 条（阈值 {t['max_queue']}）")
    unacked = stats.get("unacked") or 0
    if unacked > t["max_unacked"]:
        add("warning", "unacked_high", f"执行中未确认任务 {unacked} 条（阈值 {t['max_unacked']}），worker 可能已停")

    stream = stats.get("stream") or {}
    # lag 缺失（组不存在 / 旧版 redis / trim 后不可知）时退回 xlen 估算
    backlog = stream.get("lag")
    if backlog is None:
        backlog = stream.get("xlen") or 0
    if backlog > t["max_stream_lag"]:
        add("warning", "stream_backlog", f"访问流 Stream 未消费积压 {backlog} 条（阈值 {t['max_stream_lag']}）")
    pending = stream.get("pending") or 0
    if pending > t["max_pending"]:
        add("warning", "stream_pending", f"访问流待确认(PEL) {pending} 条（阈值 {t['max_pending']}），consumer 可能卡死或反复失败")
    for entry in stream.get("top_pending") or []:
        if entry["deliveries"] >= t["max_deliveries"]:
            add(
                "critical",
                "poison_message",
                f"访问流消息 {entry['id']} 已重投 {entry['deliveries']} 次（疑似毒消息，处理前先查 consumer 日志）",
            )

    heartbeat = stats.get("heartbeat_age")
    if heartbeat is None:
        add("critical", "heartbeat_missing", "访问流消费者心跳缺失（进程未启动或已死超过 5 分钟）")
    elif heartbeat > t["heartbeat_stale"]:
        add("warning", "heartbeat_stale", f"访问流消费者心跳已 {int(heartbeat)}s 未更新（阈值 {t['heartbeat_stale']}s）")
    return alerts
