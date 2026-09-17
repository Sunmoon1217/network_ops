"""信号处理。

1. DeviceConfig post_save：流程与 ``reparse`` 管理命令共用
   ``ops.pipeline.run_config_pipeline`` —— 从 Git 读取配置原文 → 解析器解析
   → 结果写回 config_json → 按顶层 key 分发到对应的 Saver 入库。
2. Stage post_save：阶段成功后触发下一阶段的 Celery 任务
   （collection → parsing → storage；storage 完成后收尾 Task）。
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

# 解析完成后写回 config_json 会再次触发 post_save，靠这里防重入
_processing: set[int] = set()
# Stage 状态回写会再次触发 post_save，同样防重入
_processing_stage: set[int] = set()


# ---------------------------------------------------------------------------
# Stage 阶段联动
# ---------------------------------------------------------------------------


def _trigger_next_stage(task, stage_type: str, input_data=None) -> None:
    """创建并投递下一阶段任务"""
    from core.models import Stage
    from ops.tasks import run_collection_stage, run_parsing_stage, run_storage_stage

    task_map = {
        "collection": run_collection_stage,
        "parsing": run_parsing_stage,
        "storage": run_storage_stage,
    }

    next_stage = Stage.objects.create(
        task=task,
        stage_type=stage_type,
        status="running",
        input_data=input_data or {},
    )

    task_func = task_map.get(stage_type)
    if task_func:
        task_func.delay(next_stage.pk)

    logger.info("Triggered %s stage (id=%s) for task %s", stage_type, next_stage.pk, task.pk)


@receiver(post_save, sender="core.Stage")
def on_stage_complete(sender, instance, **kwargs):
    """Stage 成功后推进到下一阶段"""
    if instance.status != "success" or instance.pk in _processing_stage:
        return

    _processing_stage.add(instance.pk)
    try:
        task = instance.task
        if instance.stage_type == "collection":
            _trigger_next_stage(task, "parsing")
        elif instance.stage_type == "parsing":
            _trigger_next_stage(task, "storage")
        elif instance.stage_type == "storage":
            type(task).objects.filter(id=task.pk).update(
                status="success",
                result={"message": "All stages completed successfully"},
            )
    except Exception as e:
        logger.error("Stage %s 联动失败: %s", instance.pk, e, exc_info=True)
    finally:
        _processing_stage.discard(instance.pk)


# ---------------------------------------------------------------------------
# DeviceConfig post_save
# ---------------------------------------------------------------------------


@receiver(post_save, sender="assets.DeviceConfig")
def on_device_config_saved(sender, instance, created, **kwargs):
    if not created or instance.pk in _processing:
        return

    _processing.add(instance.pk)
    try:
        from ops.pipeline import run_config_pipeline

        run_config_pipeline(instance.device, instance)
    except Exception as e:
        logger.error("DeviceConfig %s 处理失败: %s", instance.pk, e, exc_info=True)
    finally:
        _processing.discard(instance.pk)
