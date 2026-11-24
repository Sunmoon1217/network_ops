"""Redis 服务状态巡检（INFO 口径），web 监控页「Redis」面板轮询。

与 ``queue_monitor`` 分工：这个看 Redis 自身（内存 / 连接 / 命中率 / 键空间 / 运行时长），
那个看消费链路；两者都只读、O(1)，共用 ``access_stream.get_redis``。
Redis 不可达不抛异常（返回 ``redis_ok=False`` + ``error``）。
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
