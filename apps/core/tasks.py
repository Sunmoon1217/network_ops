"""通用任务机制：建任务、投递阶段、取消。

纯机制层：只认 ``task_type`` / ``stage_type`` 两个字符串与 ``core.task_types`` 注册表，
不认识任何业务词汇。「下一个阶段是什么」也不在这里。链路与不变量见 ``handbook/tasks.md``。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from core import task_types
from core.models import Stage, Task
from netops.celery import app as celery_app

if TYPE_CHECKING:
    from celery.app.control import Control

logger = logging.getLogger(__name__)


def dispatch(task: Task, stage_type: str, input_data: dict[str, Any] | None = None) -> Stage:
    """创建下一阶段并投递 celery 任务，返回新建的 ``Stage``。

    handler 在投递方进程内解析后 ``.delay()``——函数对象无法序列化过 broker。
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
    target_type: str = "",
    target_id: int | None = None,
    target_label: str = "",
    first_stage: str | None = None,
) -> Task:
    """创建任务并投递第一个阶段——任务工作流的唯一入口。

    ``first_stage`` 缺省由注册表按 ``task_type`` 反查。``target_*`` 是软引用，core 只存不校验。
    """
    stage_type = first_stage or task_types.first_stage_of(task_type)
    task = Task.objects.create(
        task_type=task_type,
        target_type=target_type,
        target_id=target_id,
        target_label=target_label,
        params=params or {},
        status="running",
        started_at=timezone.now(),
    )
    try:
        dispatch(task, stage_type)
    except Exception as e:
        # 投递失败必须落成 failed，否则任务永远挂在「运行中」
        Task.objects.filter(pk=task.pk).update(
            status="failed",
            error_message=f"投递 {stage_type} 阶段失败: {e}",
            completed_at=timezone.now(),
        )
        logger.exception("投递 %s 阶段失败: task=%s", stage_type, task.pk)
        raise
    return task


def cancel(task: Task) -> None:
    """取消任务：尽力撤销当前投递，然后标记为已取消。

    撤销失败不影响结果——链条会在下一个阶段边界停住（业务域信号里检查 cancelled）。
    """
    if task.celery_task_id:
        try:
            # stubs 把 control 声明成方法、运行时却是 property，cast 才能拿到 .revoke
            control = cast("Control", celery_app.control)
            control.revoke(task.celery_task_id, terminate=True)
        except Exception:
            logger.exception("撤销 celery 任务失败（忽略，靠状态检查兜底）: %s", task.celery_task_id)

    Task.objects.filter(pk=task.pk).update(status="cancelled", completed_at=timezone.now())
    logger.info("任务 %s 已取消", task.pk)


@shared_task(name=settings.INTEGRATION_PROBE_TASK)
def probe_integration_health() -> int:
    """beat 周期任务：探活全部已注册 provider，结果写 ``core.IntegrationHealth``。"""
    from core.integrations.health import probe_all

    return probe_all()
