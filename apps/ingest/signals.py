"""信号处理：DeviceConfig 与 Stage 的 post_save 联动。

1. DeviceConfig：默认**同步**跑 ``ingest.pipeline.run_config_pipeline``；批量导入会在
   save 之前挂 ``_defer_pipeline = True`` 跳过，由调用方投递 celery 链。
2. Stage：阶段成功后触发下一阶段（collection → parsing → storage，storage 完成即收尾 Task）；
   任务已取消时不再推进——这是「取消」能真正停住链条的保证。

推进表、取消语义与防重入的细节见 handbook/ingest.md
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)

# 解析完成后写回 config_json 会再次触发 post_save，靠这里防重入
_processing: set[int] = set()
# Stage 状态回写会再次触发 post_save，同样防重入
_processing_stage: set[int] = set()

# 阶段推进表（storage 是最后一个阶段，不在表里）
_NEXT_STAGE = {"collection": "parsing", "parsing": "storage"}


@receiver(post_save, sender="core.Stage")
def on_stage_complete(sender, instance, **kwargs):
    """Stage 结束后推进下一阶段；失败则收尾整个任务"""
    if instance.status not in ("success", "failed") or instance.pk in _processing_stage:
        return

    _processing_stage.add(instance.pk)
    try:
        task = instance.task

        # 任务已取消就别再往下走：revoke 撤不掉「已经在跑的那一次」，
        # 这里也避免 storage 完成后又把 cancelled 改回 success。
        if task.status == "cancelled":
            logger.info("任务 %s 已取消，停止推进 %s 阶段", task.pk, instance.stage_type)
            return

        if instance.status == "failed":
            # 阶段失败必须收尾 Task：否则任务会一直挂在「运行中」，
            # 前端只看到一个不动的进度，失败原因也只在 Stage 上。
            type(task).objects.filter(id=task.pk).update(
                status="failed",
                error_message=f"{instance.get_stage_type_display()}阶段失败: {instance.error_message}",
                completed_at=timezone.now(),
            )
            return

        next_stage = _NEXT_STAGE.get(instance.stage_type)
        if next_stage:
            from ingest.workflow import dispatch_stage

            dispatch_stage(task, next_stage)
        else:
            # storage 阶段成功 = 整个任务完成
            type(task).objects.filter(id=task.pk).update(
                status="success",
                result={"message": "All stages completed successfully"},
                completed_at=timezone.now(),
            )
    except Exception as e:
        logger.error("Stage %s 联动失败: %s", instance.pk, e, exc_info=True)
    finally:
        _processing_stage.discard(instance.pk)


@receiver(post_save, sender="assets.DeviceConfig")
def on_device_config_saved(sender, instance, created, **kwargs):
    if not created or instance.pk in _processing:
        return

    # 批量导入：调用方在 save 之前挂了 ``_defer_pipeline``，并会自己投递 celery 链
    # （解析 → 存储）。这里直接返回，避免同一个请求里串行跑几十次同步流水线。
    if getattr(instance, "_defer_pipeline", False):
        logger.info("DeviceConfig %s 标记为异步处理，跳过同步流水线", instance.pk)
        return

    _processing.add(instance.pk)
    try:
        from assets.signals import request_soft_asset_sync
        from ingest.pipeline import run_config_pipeline

        result = run_config_pipeline(instance.device, instance)
        # 配置行可能被 Saver 改过 → 请求刷新域名 / 负载均衡资产（事务提交后执行）
        if result.outcomes:
            request_soft_asset_sync("DeviceConfig 同步解析入库")
    except Exception as e:
        logger.error("DeviceConfig %s 处理失败: %s", instance.pk, e, exc_info=True)
    finally:
        _processing.discard(instance.pk)
