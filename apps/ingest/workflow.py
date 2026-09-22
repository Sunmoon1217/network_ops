"""任务工作流的入口：启动、阶段投递、取消。

阶段之间的推进（collection → parsing → storage）由 ``ingest/signals.py`` 监听 Stage 完成
事件完成；这里负责**最初的投递**与取消，让「投递」这件事只存在一处。

单独成文件而不是塞进 ``ingest/tasks.py``：那里是纯 celery 任务定义（``@shared_task`` 的壳），
这里是同步的编排 API——建 Task、投下一阶段、把 DeviceConfig 的解析投成链、取消。

导入只按一条线分两处——**运行期是否真的用到这个名字**：``Stage`` / ``Task`` 要调
``.objects``，所以放模块顶部；``assets.models.Device`` 只出现在类型注解里，放
``TYPE_CHECKING``（注解因此写成字符串，否则运行期求值时它是未定义的名字）。
代价是本模块依赖 app registry，只能在 ``django.setup()`` 之后导入；它的四个导入点
（两个视图、一个信号、一个序列化器）都在运行期，不涉及 app 加载期。
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
# 值标成 Any 是有意的：celery-stubs 把 ``@shared_task`` 装饰后的函数仍声明为普通函数，
# 且它的 ``Task`` 上**没有 delay**（只有 si / s / apply_async），所以只有 Any 能让
# ``.delay()`` 通过类型检查，而不必写 ``# type: ignore``。
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
    # celery-stubs 把 @shared_task 装饰后的函数仍声明成普通函数（``Callable[[F], F]``），
    # 而运行时它其实是 Task 实例（有 .si/.delay）。这里显式 cast 回 Task：既让类型检查通过，
    # 又保住对 ``.si`` 这个名字的检查（比 ``# type: ignore`` 好）。
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
            # celery-stubs 把 ``Celery.control`` 声明成了方法（``def control(self): ...``），
            # 而它在运行时是 property（返回 Control 实例，**不能调用**）——所以这里 cast 回
            # 真正的 Control 类型，才能拿到 .revoke 且不写错成 control()。
            control = cast("Control", celery_app.control)
            control.revoke(task.celery_task_id, terminate=True)
        except Exception:
            logger.exception("撤销 celery 任务失败（忽略，靠状态检查兜底）: %s", task.celery_task_id)

    Task.objects.filter(pk=task.pk).update(status="cancelled", completed_at=timezone.now())
    logger.info("任务 %s 已取消", task.pk)
