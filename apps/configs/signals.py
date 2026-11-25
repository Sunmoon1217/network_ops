"""软资产刷新信号（T4）：配置行变化后自动重跑归并。

配置侧解析 / 存储完成后调用 ``request_soft_asset_sync()``；接收器在**事务提交后**执行，
同一事务只跑最后一次，失败只记日志。归属与理由见 handbook/assets.md「归并链路」。
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
    from configs.services.soft_asset_sync import sync_soft_assets

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
