"""软资产归并的**编排**：先算（configs）后写（assets），同一事务、一把咨询锁。

两步必须在同一事务里串起来，不能拆成「算完 → Celery → 写」：

1. 事务原子性——拆开后计算与写入分属两个事务，中间有窗口期；
2. ``pg_advisory_xact_lock`` 是**事务级**锁，跨进程无效；拆开就得换 session 级锁或 Redis；
3. 锁的粒度——现在是「整个归并串行」，拆开后只有写入阶段串行，计算阶段可能并发。

依赖方向也因此干净：``configs → assets``（矩阵允许，上层调下层的写入能力），
``assets`` 完全不认识 configs。
"""

from __future__ import annotations

from django.db import connection, transaction

from assets.services.soft_asset_sync import SyncStats, apply_soft_assets
from configs.services import soft_asset_builder as builder

__all__ = ["SyncStats", "sync_domain_assets", "sync_load_balancer_services", "sync_soft_assets"]

#: 归并的事务级咨询锁 key（"SOFT"）：信号（多 worker）与管理命令共用，避免并发
#: ``get_or_create`` 撞唯一约束。项目强绑 PostgreSQL，直接用。
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


@transaction.atomic
def sync_soft_assets(asset_type: str = "all") -> SyncStats:
    """``asset_type``：``all`` / ``domain`` / ``lb``。

    整个归并在一把事务级咨询锁里执行：Celery 多 worker 与管理命令并发时串行，
    后到者会看到前者的结果，``get_or_create`` 不会撞唯一约束。
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_SYNC_LOCK_KEY])

    stats = SyncStats()
    if asset_type in ("all", "domain"):
        stats.merge(sync_domain_assets())
    if asset_type in ("all", "lb"):
        stats.merge(sync_load_balancer_services())
    return stats
