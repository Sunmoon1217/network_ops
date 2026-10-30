"""Celery worker 与任务巡检（inspect 口径），web 监控页「Celery」面板轮询。

数据源是 ``celery_app.control.inspect(timeout=...)`` 的**只读**广播（ping / stats /
active / reserved / scheduled），回答三个问题：

- **worker 谁活着**：``ping()`` 的应答者名单 + ``stats()`` 的并发池与已处理量——
  worker 全挂时 inspect 返回 None/空，这正是要显式报出来的状态（2026-10 事故里
  consumer OOM 循环、无人知道 worker 还在不在）；
- **在跑什么**：``active()`` 每个 worker 正在执行的任务（id / 名称 / 开始时间 / 已跑秒数）；
- **排队什么**：``reserved()``（已取走未开跑）与 ``scheduled()``（eta/countdown 延迟）。

口径注意：

- inspect 走 **broker 广播**，每个方法一次请求-应答、超时即空——所以四个方法各自
  try/except，一段拿不到不影响其余段；``workers`` 为空 ≠ 报错，是「没有 worker 应答」，
  由前端按 ``ok``/``workers`` 空名单如实展示；
- 任务的 ``args``/``kwargs`` 原样透传字符串（json 反序列化后的 repr 不可靠且可能很大），
  这里对超长内容截断，避免把整份配置塞进响应；
- 本模块**只读**：不 revoke、不 terminate、不改任何任务状态（cancel 走 /api/tasks/<id>/cancel/）。

Redis 不可达 / broker 无应答时**不抛异常**：返回 ``ok=False`` + ``error``（与
``queue_monitor`` 同款哲学——监控自身炸掉比被监控对象炸掉更没意义）。
"""

from __future__ import annotations

import time
from logging import getLogger

from netops.celery import app as celery_app

logger = getLogger(__name__)

#: inspect 广播超时（秒）：应答在健康 broker 上是毫秒级，这只是「多久没动静算没有」。
#:
#: 为什么是 0.5 而不是更长：kombu 的收包循环在**没有 limit** 时，收满现有应答后还要把
#: 整个 timeout 等满才返回（见 collect docstring）——ping 这一步省不掉这一次等待，而
#: 前端 axios 是 10s。0.5s × (1 次 ping + 其余段) 远在预算内；worker 从 ping 到
#: pong 的 RTT 是局域网毫秒级，0.5s 对健康集群绰绰有余。
INSPECT_TIMEOUT = 0.5

#: active 任务的 args/kwargs 展示上限（字符），防整份配置原文进响应
_ARG_CLIP = 200


def _clip(value, limit: int = _ARG_CLIP) -> str:
    """任务参数转展示字符串，超长截断（原样 repr，不做反序列化）。"""
    text = "" if value is None else str(value)
    return text if len(text) <= limit else text[:limit] + "…"


def _task_brief(task: dict, extra: dict | None = None) -> dict:
    """inspect 返回的任务字典 → 前端行（id/名称/参数/worker/时间）。"""
    brief = {
        "id": str(task.get("id") or ""),
        "name": str(task.get("name") or ""),
        "args": _clip(task.get("args")),
        "kwargs": _clip(task.get("kwargs")),
        "worker": str(task.get("hostname") or task.get("worker") or ""),
    }
    if extra:
        brief.update(extra)
    return brief


def _workers(stats: dict, ping: dict) -> list[dict]:
    """worker 名单：ping 应答者（活性）+ stats 的并发/已处理量（容量）。"""
    rows = []
    for name in sorted(ping or {}):
        info = (stats or {}).get(name) or {}
        pool = info.get("pool") or {}
        total = info.get("total") or {}
        rows.append(
            {
                "name": name,
                "concurrency": int(pool.get("max-concurrency") or 0),
                "processed": sum(int(v) for v in total.values()) if isinstance(total, dict) else 0,
                "status": "online",
            }
        )
    return rows


def collect(inspector=None) -> dict:
    """采集一轮 Celery worker / 任务全貌（只读）；broker 无应答降级为 ok=False。

    为什么两段式 inspector（别改回一个）：kombu 的收包循环在**没有 limit** 时收满
    现有应答后还会把 timeout 等满才返回（它不知道还会有谁应答）——5 个方法各等
    一次 = 5 × timeout，曾经 5 × 3s = 15s 撞穿前端 axios 10s 超时，页面只显示
    「接口不可达」。所以先用 ping 问出 worker 数（这一步省不掉，只能等满一次），
    后续调用带 ``limit=len(ping)``：收满应答立即返回，不再空等。
    """
    injected = inspector is not None
    inspector = inspector or celery_app.control.inspect(timeout=INSPECT_TIMEOUT)
    stats: dict = {
        "checked_at": time.time(),
        "ok": True,
        "error": None,
        "workers": [],
        "active": [],
        "reserved": [],
        "scheduled": [],
    }

    def safe(fn, fallback=None):
        """一段 inspect 挂掉只空那一段（打日志、不打断其余段）。"""
        try:
            return fn()
        except Exception:
            logger.warning("Celery inspect 分段读取失败（忽略）", exc_info=True)
            return fallback

    try:
        ping = inspector.ping() or {}
    except Exception as exc:
        logger.warning("Celery 巡检失败", exc_info=True)
        stats["ok"] = False
        stats["error"] = str(exc)
        return stats
    if not ping:
        stats["ok"] = False
        stats["error"] = "没有 worker 应答（进程未启动或 broker 不可达）"
        return stats
    if not injected:
        # limit=worker 数：收满应答立即返回（语义见 docstring）
        inspector = celery_app.control.inspect(timeout=INSPECT_TIMEOUT, limit=len(ping))

    stats["workers"] = _workers(safe(inspector.stats, {}) or {}, ping)
    now = time.time()
    for worker, tasks in (safe(inspector.active, {}) or {}).items():
        for task in tasks or []:
            started = float(task.get("time_start") or 0)
            stats["active"].append(
                _task_brief(task, {"started": started, "runtime": round(now - started, 1) if started else None})
            )
    for worker, tasks in (safe(inspector.reserved, {}) or {}).items():
        for task in tasks or []:
            stats["reserved"].append(_task_brief(task))
    for worker, entries in (safe(inspector.scheduled, {}) or {}).items():
        for entry in entries or []:
            # scheduled 条目是 {eta, priority, request: {...}}，任务本体在 request 里
            request = entry.get("request") or entry
            stats["scheduled"].append(_task_brief(request, {"eta": entry.get("eta")}))
    return stats
