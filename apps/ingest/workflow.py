"""任务工作流的入口：启动、阶段投递、取消。

阶段之间的推进由 ``ingest/signals.py`` 监听 Stage 完成事件完成；这里负责**最初的投递**
与取消，让「投递」只存在一处。与 ``tasks.py`` 的分工：那里是纯 celery 任务定义
（``@shared_task`` 的壳），这里是同步编排 API。

导入位置按「运行期是否真的用到这个名字」分两处：``Stage`` / ``Task`` 要调 ``.objects``
放模块顶部，只出现在注解里的 ``Device`` 放 ``TYPE_CHECKING``。代价是本模块只能在
``django.setup()`` 之后导入（现有导入点都在运行期）。
"""

import logging
from typing import TYPE_CHECKING, Any, cast

from celery import chain
from django.utils import timezone

from core.models import Stage, Task
from ingest.tasks import (
    run_collection_stage,
    run_config_parsing,
    run_config_storage,
    run_parsing_stage,
    run_storage_stage,
)
from netops.celery import app as celery_app

if TYPE_CHECKING:
    from celery import Task as CeleryTask
    from celery.app.control import Control

    from assets.models import Device

logger = logging.getLogger(__name__)

# 阶段推进表（collection → parsing → storage）。
# 值标 Any 是有意的：celery-stubs 把 @shared_task 装饰后的函数仍当普通函数，且它的
# Task 上没有 delay，只有 Any 能让 .delay() 过检，而不必写 type: ignore。
_STAGE_TASKS: dict[str, Any] = {
    "collection": run_collection_stage,
    "parsing": run_parsing_stage,
    "storage": run_storage_stage,
}


def dispatch_stage(task: Task, stage_type: str, input_data: dict[str, Any] | None = None) -> Stage:
    """创建下一阶段并投递 celery 任务。

    ``Task.celery_task_id`` 会被更新成**最近一次**投递的任务 id：一个任务要推进多个
    阶段，这个字段表达「当前在跑的那次投递」，用于排错与取消。
    """
    stage = Stage.objects.create(
        task=task,
        stage_type=stage_type,
        status="running",
        input_data=input_data or {},
    )
    async_result = _STAGE_TASKS[stage_type].delay(stage.pk)
    Task.objects.filter(pk=task.pk).update(celery_task_id=async_result.id)
    logger.info("已投递 %s 阶段 stage=%s celery=%s task=%s", stage_type, stage.pk, async_result.id, task.pk)
    return stage


def start_task(device: "Device", task_type: str, params: dict[str, Any] | None = None) -> Task:
    """创建任务并投递第一个阶段（采集）——这是任务工作流的唯一入口。"""
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
    # 运行时它们是 Task 实例（有 .si/.delay），stubs 只看成普通函数：cast 比 type: ignore
    # 好，因为保住了对 .si 这个名字的检查。
    parsing = cast("CeleryTask", run_config_parsing)
    storage = cast("CeleryTask", run_config_storage)

    chain(parsing.si(config_id), storage.si(config_id)).apply_async()
    logger.info("已投递配置解析链: DeviceConfig %s", config_id)


def cancel_task(task: Task) -> None:
    """取消任务：尽力撤销当前 celery 投递，然后把任务标成已取消。

    撤销是**尽力而为**的（需要 worker 在线且 broker 可达）。真正保证链条停下的是
    ``ingest/signals.py`` 在阶段完成时的「任务已取消就不再推进」检查——所以即使撤不掉
    正在跑的那一次，它也会在下一个阶段边界停住。
    """
    if task.celery_task_id:
        try:
            # stubs 把 Celery.control 声明成方法，运行时却是 property（返回 Control，
            # **不能调用**）：cast 才拿得到 .revoke 又不会写错成 control()。
            control = cast("Control", celery_app.control)
            control.revoke(task.celery_task_id, terminate=True)
        except Exception:
            logger.exception("撤销 celery 任务失败（忽略，靠状态检查兜底）: %s", task.celery_task_id)

    Task.objects.filter(pk=task.pk).update(status="cancelled", completed_at=timezone.now())
    logger.info("任务 %s 已取消", task.pk)
