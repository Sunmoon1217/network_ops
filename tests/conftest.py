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


# ---------------------------------------------------------------------------
# 用户权限（core.permissions.IsOperatorOrReadOnly）的测试基建
# ---------------------------------------------------------------------------


@pytest.fixture
def normal_user(db):
    """普通用户（role=normal）：登录后只读。"""
    from core.models import User

    return User.objects.create_user(username="_t_reader", password="x")


@pytest.fixture
def operator_user(db):
    """操作员（role=operator）：登录后可读可写。"""
    from core.models import User

    return User.objects.create_user(username="_t_operator", password="x", role="operator")


@pytest.fixture
def api_client(normal_user):
    """已认证的**普通用户**客户端（只读）——读接口测试用它，
    顺带验证「普通用户能查询」这条权限契约。"""
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=normal_user)
    return client


@pytest.fixture
def operator_client(operator_user):
    """已认证的**操作员**客户端（读写）——写接口测试用它。"""
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=operator_user)
    return client
