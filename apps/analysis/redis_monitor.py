"""Redis 服务状态巡检（INFO 口径），web 监控页「Redis」面板轮询。

与 ``queue_monitor`` 的分工：那个看**消费链路**（队列长度 / Stream lag / PEL / 心跳，
回答「活儿堆了多少」），这个看 **Redis 服务本身**（内存 / 连接 / 命中率 / 键空间 /
运行时长，回答「Redis 自己健不健康」）。两者的采集都是只读、O(1)，共用
``access_stream.get_redis``，可被同一页面并行轮询。

指标口径（INFO 里挑出来给前端的子集）：

- ``server``：版本 / 运行模式 / 已运行秒数——「是不是预期的那个实例」；
- ``memory``：used / peak / rss / 碎片率 / maxmemory 与**使用率**（maxmemory=0
  即不限制时使用率为 null，别把「不限」画成 0%）；
- ``clients``：已连接 / 阻塞（BLPOP 等）/ 上限——连接数顶到 maxclients 是典型事故；
- ``stats``：每秒命令数 / 命中率（hits/(hits+misses)，两者皆 0 时 null）/ 逐出 / 过期——
  命中率骤降 + 逐出飙升 = 内存不够开始踢键；
- ``keyspace``：各 db 的键数与带 TTL 的键数，``dbsize`` 是当前 db 总数。

Redis 不可达时**不抛异常**（与 queue_monitor 同款哲学）：返回 ``redis_ok=False``
+ ``error``，监控自身炸掉比被监控对象炸掉更没意义。
"""

from __future__ import annotations

import time
from logging import getLogger

from analysis.access_stream import get_redis

logger = getLogger(__name__)

#: 内存使用率告警线（used/maxmemory；仅展示口径，阈值判定在前端/告警侧）
MEMORY_WARN_RATIO = 0.8


def _hit_rate(hits: int, misses: int) -> float | None:
    """缓存命中率（0~1 保留 4 位）；样本皆 0（没跑过读）时返回 None 而不是 0。"""
    total = hits + misses
    return round(hits / total, 4) if total else None


def _keyspace(info: dict) -> dict:
    """INFO 的 keyspace 段（db0: {...}）→ {dbs: {db: {keys, expires}}, total_keys}。"""
    dbs: dict[str, dict] = {}
    total = 0
    for key, value in info.items():
        if not key.startswith("db") or not isinstance(value, dict):
            continue
        keys = int(value.get("keys") or 0)
        dbs[key] = {"keys": keys, "expires": int(value.get("expires") or 0)}
        total += keys
    return {"dbs": dbs, "total_keys": total}


def collect(client=None) -> dict:
    """采集一轮 Redis 服务状态（只读）；键缺失按 0 / None 处理，不抛异常。"""
    client = client or get_redis()
    stats: dict = {"checked_at": time.time(), "redis_ok": True, "error": None}
    try:
        info = client.info()
        maxmemory = int(info.get("maxmemory") or 0)
        used = int(info.get("used_memory") or 0)
        hits = int(info.get("keyspace_hits") or 0)
        misses = int(info.get("keyspace_misses") or 0)
        stats["server"] = {
            "version": info.get("redis_version"),
            "mode": info.get("redis_mode"),
            "uptime_seconds": int(info.get("uptime_in_seconds") or 0),
        }
        stats["memory"] = {
            "used_bytes": used,
            "used_human": info.get("used_memory_human"),
            "peak_human": info.get("used_memory_peak_human"),
            "rss_human": info.get("used_memory_rss_human"),
            "fragmentation": float(info.get("mem_fragmentation_ratio") or 0),
            "maxmemory_human": info.get("maxmemory_human"),
            # maxmemory=0（不限制）时使用率不可算，给 null 而不是 0——「不限」不是「空」
            "used_ratio": round(used / maxmemory, 4) if maxmemory else None,
        }
        stats["clients"] = {
            "connected": int(info.get("connected_clients") or 0),
            "blocked": int(info.get("blocked_clients") or 0),
            "maxclients": int(info.get("maxclients") or 0),
        }
        stats["stats"] = {
            "ops_per_sec": int(info.get("instantaneous_ops_per_sec") or 0),
            "total_commands": int(info.get("total_commands_processed") or 0),
            "hits": hits,
            "misses": misses,
            "hit_rate": _hit_rate(hits, misses),
            "evicted_keys": int(info.get("evicted_keys") or 0),
            "expired_keys": int(info.get("expired_keys") or 0),
        }
        stats["keyspace"] = {**_keyspace(info), "dbsize": int(client.dbsize())}
    except Exception as exc:
        logger.warning("Redis 状态采集失败", exc_info=True)
        stats["redis_ok"] = False
        stats["error"] = str(exc)
    return stats
