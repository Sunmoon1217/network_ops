"""共享 fixture。"""

import pytest


@pytest.fixture
def eager_celery(settings):
    """让 celery 任务在进程内同步执行，且失败时把状态反映到 result 而不是抛异常。

    任务失败必须让 ``result.state`` 是 FAILURE（见 tests/ops/test_celery_tasks.py），
    所以这里把 ``task_eager_propagates`` 关掉。
    """
    from netops.celery import app

    prev = (app.conf.task_always_eager, app.conf.task_eager_propagates)
    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = False
    yield app
    app.conf.task_always_eager, app.conf.task_eager_propagates = prev
