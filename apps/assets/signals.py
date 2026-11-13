"""软资产刷新信号（T4）：配置行变化后自动重跑归并。

配置侧（``ingest``）在解析 / 存储完成后调用 ``request_soft_asset_sync()``，表示
``GtmWideip`` / ``LtmVirtualServer`` 等配置行可能已变。这里做三件事：

1. **事务提交后执行**：解析过程会回写 ``config_json``、批量写多张配置表，提交前归并会
   读到中间态，所以统一用 ``transaction.on_commit``。
2. **同批合并**：一个事务里可能多次请求（多设备 / 多 Saver），用单调递增的 revision
   只执行最后一次；回滚不会把标记卡死（下一次请求带新 revision）。
3. **跨进程串行**：并发由 ``sync_soft_assets`` 内部的事务级咨询锁保证，这里不重复加锁。

归并失败只记日志、不抛出：配置入库本身已经成功，不能因为派生资产刷新失败而回滚或
让 Celery 任务失败。需要补救时跑 ``manage.py sync_soft_assets`` 全量重建。
"""

import logging

from django.db import transaction
from django.dispatch import Signal, receiver

logger = logging.getLogger(__name__)

#: 配置侧请求刷新软资产；``reason`` 只用于日志定位
soft_assets_stale = Signal()

#: 同一进程内的请求序号：同批提交时只让最后一次真正执行
_revision = 0


def request_soft_asset_sync(reason: str = "") -> None:
    """配置行变化后调用；可重复调用，同一个事务只跑最后一次归并。"""
    soft_assets_stale.send(sender=request_soft_asset_sync, reason=reason)


def _run_sync() -> None:
    from assets.services.soft_asset_sync import sync_soft_assets

    try:
        stats = sync_soft_assets()
        logger.info(
            "软资产已刷新：新增 %s，更新 %s，未变 %s，跳过 %s",
            stats.created,
            stats.updated,
            stats.unchanged,
            stats.skipped,
        )
    except Exception:
        logger.exception("软资产刷新失败，可执行 manage.py sync_soft_assets 重建")


@receiver(soft_assets_stale)
def _on_soft_assets_stale(sender, reason: str = "", **kwargs):
    global _revision
    _revision += 1
    current = _revision

    def _run_if_latest() -> None:
        # 同事务里更晚的请求已经排在后面执行；这里直接跳过，避免重复全量归并
        if current == _revision:
            _run_sync()

    transaction.on_commit(_run_if_latest)
