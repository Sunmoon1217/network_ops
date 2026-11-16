"""通用任务机制：建任务、投递阶段、取消。

这一层是**纯机制**：它只认 ``task_type`` / ``stage_type`` 两个字符串与
``core.task_types`` 注册表，不认识任何业务词汇（见 ``handbook/design/task-framework.md``）。

链路（状态存 PostgreSQL，Redis 只是投递通道）：

    create_task()  写 Task(status=running) → dispatch(首个 stage)
        ↓
    dispatch()     写 Stage(status=running) → 从注册表取 handler → .delay()
        ↓
    worker 执行阶段任务 → UPDATE Stage/Task → Stage 的 post_save 信号推进下一阶段

「下一个阶段是什么」属于业务链路知识，不在本模块——由业务域的信号接收器决定
（现状在 ``ingest/signals.py`` 的 ``_NEXT_STAGE``）。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from django.db import models
from django.utils import timezone

from core import task_types
from core.models import Stage, Task
from netops.celery import app as celery_app

if TYPE_CHECKING:
    from celery.app.control import Control

logger = logging.getLogger(__name__)


def dispatch(task: Task, stage_type: str, input_data: dict[str, Any] | None = None) -> Stage:
    """创建下一阶段并投递 celery 任务。

    handler 按 ``stage_type`` 从注册表解析——**在投递方进程内解析**，因为函数对象
    无法序列化过 broker；本函数自己永远不是 celery 任务。

    ``Task.celery_task_id`` 会被更新成**最近一次**投递的任务 id：一个任务要推进多个
    阶段，这个字段表达「当前在跑的那次投递」，用于排错与取消。
    """
    stage = Stage.objects.create(
        task=task,
        stage_type=stage_type,
        status="running",
        input_data=input_data or {},
    )
    handler = task_types.handler_for(stage_type)
    async_result = handler.delay(stage.pk)
    Task.objects.filter(pk=task.pk).update(celery_task_id=async_result.id)
    logger.info("已投递 %s 阶段 stage=%s celery=%s task=%s", stage_type, stage.pk, async_result.id, task.pk)
    return stage


def create_task(
    task_type: str,
    *,
    params: dict[str, Any] | None = None,
    device: models.Model | None = None,
    first_stage: str | None = None,
) -> Task:
    """创建任务并投递第一个阶段——任务工作流的唯一入口。

    ``first_stage`` 缺省由注册表按 ``task_type`` 反查，所以调用方（core 的 API 层）
    不必知道「采集任务的第一个阶段叫 collection」。
    """
    stage_type = first_stage or task_types.first_stage_of(task_type)
    task = Task.objects.create(
        task_type=task_type,
        device=device,
        params=params or {},
        status="running",
        started_at=timezone.now(),
    )
    try:
        dispatch(task, stage_type)
    except Exception as e:
        # 投递失败（broker 不可达是最常见的）必须把任务落成 failed，
        # 否则它会永远挂在「运行中」，前端只能看到一个不动的进度。
        Task.objects.filter(pk=task.pk).update(
            status="failed",
            error_message=f"投递 {stage_type} 阶段失败: {e}",
            completed_at=timezone.now(),
        )
        logger.exception("投递 %s 阶段失败: task=%s", stage_type, task.pk)
        raise
    return task


def cancel(task: Task) -> None:
    """取消任务：尽力撤销当前 celery 投递，然后把任务标成已取消。

    撤销是**尽力而为**的（需要 worker 在线且 broker 可达）。真正保证链条停下的是
    业务域的阶段推进信号里那句「任务已取消就不再推进」的检查——所以即使撤不掉
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
