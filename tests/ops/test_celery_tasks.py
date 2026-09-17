"""Celery 阶段任务的失败传播回归测试。

守护一条约束：阶段任务失败时，**数据库里的 Stage 与 Celery 的任务状态必须一致**。
历史缺陷：``apps/ops/tasks.py`` 三个阶段任务的 except 只写 ``_update_stage_status``
而漏了 ``raise``，导致 Stage=failed 但 ``task.state`` 仍是 SUCCESS，
AsyncResult / Flower 的失败告警与重试全部失效。
"""

import pytest

from core.models import Stage, Task
from ops.tasks import run_collection_stage, run_parsing_stage


@pytest.fixture
def eager_celery(settings):
    """让任务在进程内同步执行，且失败时把状态反映到 result 而不是抛异常。"""
    from netops.celery import app

    prev = (app.conf.task_always_eager, app.conf.task_eager_propagates)
    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = False
    yield app
    app.conf.task_always_eager, app.conf.task_eager_propagates = prev


@pytest.mark.django_db
def test_collection_failure_marks_task_as_failure(eager_celery):
    """设备无可用连接 → 采集阶段失败，Celery 状态必须是 FAILURE。"""
    from assets.models import Device

    device = Device.objects.create(hostname="celery-fail-no-conn", device_type="switch")
    task = Task.objects.create(task_type="collect_config", device=device)
    stage = Stage.objects.create(task=task, stage_type="collection")

    result = run_collection_stage.delay(stage.pk)

    stage.refresh_from_db()
    assert stage.status == "failed"
    assert stage.error_message
    assert result.state == "FAILURE", "阶段失败必须向上抛，否则 Celery 会记成 SUCCESS"


@pytest.mark.django_db
def test_parsing_failure_marks_task_as_failure(eager_celery):
    """无成功的采集阶段 → 解析阶段失败，Celery 状态必须是 FAILURE。"""
    from assets.models import Device

    device = Device.objects.create(hostname="celery-fail-no-collection", device_type="switch")
    task = Task.objects.create(task_type="collect_config", device=device)
    stage = Stage.objects.create(task=task, stage_type="parsing")

    result = run_parsing_stage.delay(stage.pk)

    stage.refresh_from_db()
    assert stage.status == "failed"
    assert result.state == "FAILURE", "阶段失败必须向上抛，否则 Celery 会记成 SUCCESS"
