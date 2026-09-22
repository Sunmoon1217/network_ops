"""共享 fixture。"""

import pytest


@pytest.fixture(autouse=True)
def access_flow_dispatch_off(settings):
    """测试默认不投递 AccessFlow 重建任务。

    PolicySaver 每次保存都会调 ``request_rebuild``；不禁用的话，跑测试时会把消息
    发进本机真实 Redis（dev 环境常常正跑着 compose 的 redis）。需要验证投递行为的
    测试自己打开开关：``settings.ACCESS_FLOW_DISPATCH = True``。
    """
    settings.ACCESS_FLOW_DISPATCH = False


@pytest.fixture
def eager_celery(settings):
    """让 celery 任务在进程内同步执行，且失败时把状态反映到 result 而不是抛异常。

    任务失败必须让 ``result.state`` 是 FAILURE（见 tests/ingest/test_celery_tasks.py），
    所以这里把 ``task_eager_propagates`` 关掉。
    """
    from netops.celery import app

    prev = (app.conf.task_always_eager, app.conf.task_eager_propagates)
    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = False
    yield app
    app.conf.task_always_eager, app.conf.task_eager_propagates = prev
