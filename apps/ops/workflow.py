"""任务工作流的入口：启动、阶段投递、取消。

阶段之间的推进（collection → parsing → storage）由 ``ops/signals.py`` 监听 Stage 完成
事件完成；这里负责**最初的投递**与取消，让「投递」这件事只存在一处。

单独成文件而不是塞进 ``ops/tasks.py``：那个模块是纯 celery 任务定义，导入即拉起
celery；而视图侧只需要一个同步的入口函数。
"""

import logging
from typing import TYPE_CHECKING, Any

from django.utils import timezone

if TYPE_CHECKING:
    from assets.models import Device
    from core.models import Stage, Task

logger = logging.getLogger(__name__)


def _stage_tasks() -> dict[str, Any]:
    """延迟导入任务函数，避免模块导入期就加载 celery。"""
    from ops.tasks import run_collection_stage, run_parsing_stage, run_storage_stage

    return {
        "collection": run_collection_stage,
        "parsing": run_parsing_stage,
        "storage": run_storage_stage,
    }


def dispatch_stage(task: "Task", stage_type: str, input_data: dict[str, Any] | None = None) -> "Stage":
    """创建下一阶段并投递 celery 任务。

    ``Task.celery_task_id`` 会被更新成**最近一次**投递的任务 id：一个任务要推进多个
    阶段，这个字段表达「当前在跑的那次投递」，用于排错与取消。
    """
    from core.models import Stage, Task

    stage = Stage.objects.create(
        task=task,
        stage_type=stage_type,
        status="running",
        input_data=input_data or {},
    )
    async_result = _stage_tasks()[stage_type].delay(stage.pk)
    Task.objects.filter(pk=task.pk).update(celery_task_id=async_result.id)
    logger.info("已投递 %s 阶段 stage=%s celery=%s task=%s", stage_type, stage.pk, async_result.id, task.pk)
    return stage


def start_task(device: "Device", task_type: str, params: dict[str, Any] | None = None) -> "Task":
    """创建任务并投递第一个阶段（采集）——这是任务工作流的唯一入口。"""
    from core.models import Task

    task = Task.objects.create(
        task_type=task_type,
        device=device,
        params=params or {},
        status="running",
        started_at=timezone.now(),
    )
    try:
        dispatch_stage(task, "collection")
    except Exception as e:
        # 投递失败（broker 不可达是最常见的）必须把任务落成 failed，
        # 否则它会永远挂在「运行中」，前端只能看到一个不动的进度。
        Task.objects.filter(pk=task.pk).update(
            status="failed",
            error_message=f"投递采集任务失败: {e}",
            completed_at=timezone.now(),
        )
        logger.exception("投递采集任务失败: task=%s", task.pk)
        raise
    return task


def submit_config_job(config_id: int) -> None:
    """把一条 DeviceConfig 的「解析 → 存储」投递成 celery 链（批量导入用）。

    两个任务都要拿到 ``config_id``，所以第二个用 ``.si()``（immutable）：默认的 ``.s()``
    会把上一个任务的返回值当参数传下去，而解析任务的返回值是 None。
    """
    from celery import chain

    from ops.tasks import run_config_parsing, run_config_storage

    chain(run_config_parsing.si(config_id), run_config_storage.si(config_id)).apply_async()
    logger.info("已投递配置解析链: DeviceConfig %s", config_id)


def cancel_task(task: "Task") -> None:
    """取消任务：尽力撤销当前 celery 投递，然后把任务标成已取消。

    撤销是**尽力而为**的（需要 worker 在线且 broker 可达）。真正保证链条停下的是
    ``ops/signals.py`` 在阶段完成时的「任务已取消就不再推进」检查——所以即使撤不掉
    正在跑的那一次，它也会在下一个阶段边界停住。
    """
    from core.models import Task

    if task.celery_task_id:
        try:
            from netops.celery import app as celery_app

            celery_app.control.revoke(task.celery_task_id, terminate=True)
        except Exception:
            logger.exception("撤销 celery 任务失败（忽略，靠状态检查兜底）: %s", task.celery_task_id)

    Task.objects.filter(pk=task.pk).update(status="cancelled", completed_at=timezone.now())
    logger.info("任务 %s 已取消", task.pk)
