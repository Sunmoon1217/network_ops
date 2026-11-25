"""软资产归并的编排：先算（configs）后写（assets），同一事务、一把咨询锁。

两步不能拆成「算完 → Celery → 写」：原子性、锁粒度与依赖方向都会被破坏。
细节见 handbook/assets.md「归并链路」。
"""

from __future__ import annotations

from django.db import connection, transaction

from assets.services.db_locks import mysql_named_lock
from assets.services.softasset import SyncStats, apply_soft_assets
from configs.services.softasset import build as builder

__all__ = ["SyncStats", "sync_domain_assets", "sync_load_balancer_services", "sync_soft_assets"]

#: PG 的事务级咨询锁 key（"SOFT"）：信号（多 worker）与管理命令共用，避免并发
#: ``get_or_create`` 撞唯一约束；MySQL 走 ``mysql_named_lock`` 的会话级命名锁。
_SYNC_LOCK_KEY = 0x534F4654


def _build_and_apply(result: builder.BuildResult) -> SyncStats:
    stats = apply_soft_assets(result.drafts)
    stats.skipped += result.skipped
    return stats


@transaction.atomic
def sync_domain_assets() -> SyncStats:
    """``GtmWideip`` → 域名资产：按 FQDN 跨设备归并。"""
    return _build_and_apply(builder.build_domain_drafts())


@transaction.atomic
def sync_load_balancer_services() -> SyncStats:
    """``LtmVirtualServer`` → 负载均衡服务资产：按 ``VIP#port`` 跨设备归并。"""
    return _build_and_apply(builder.build_lb_drafts())


def sync_soft_assets(asset_type: str = "all") -> SyncStats:
    """``asset_type``：``all`` / ``domain`` / ``lb``。

    整个归并在一把咨询锁里执行：Celery 多 worker 与管理命令并发时串行，
    后到者会看到前者的结果，``get_or_create`` 不会撞唯一约束。
    PG 用事务级 advisory lock（随事务释放）；MySQL 用会话级 GET_LOCK，
    锁放在事务外层，等事务提交后再释放（``mysql_named_lock``）。
    """
    with mysql_named_lock("soft_asset_sync"):
        with transaction.atomic():
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_SYNC_LOCK_KEY])

            stats = SyncStats()
            if asset_type in ("all", "domain"):
                stats.merge(sync_domain_assets())
            if asset_type in ("all", "lb"):
                stats.merge(sync_load_balancer_services())
            return stats
