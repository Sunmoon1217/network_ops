"""任务 / 阶段接口。

这两个资源此前只有模型与 celery 任务、没有任何接口，导致「采集→解析→存储」那条
工作流在产品里**不可达**（没人创建最初的 Task/Stage，信号也就永不触发）。
"""

import pytest
from rest_framework.test import APIClient

from assets.models import Device, DeviceConnection, DeviceModel, Vendor
from core.models import Stage, Task, User
from ingest import workflow

TASKS_URL = "/api/tasks/"


@pytest.fixture
def client(db):
    user = User.objects.create_user(username="_t_task_api", password="x")
    api = APIClient()
    api.force_authenticate(user=user)
    return api


@pytest.fixture
def device(db):
    vendor, _ = Vendor.objects.get_or_create(name="H3C")
    model, _ = DeviceModel.objects.get_or_create(name="M-task", vendor=vendor)
    return Device.objects.create(hostname="_t_task_dev", device_type="switch", device_model=model)


def _no_dispatch(monkeypatch):
    """让投递失败：阶段表里的任务换成 ``.delay()`` 抛异常的桩（模拟 broker 不可达）。"""

    class _FailTask:
        @staticmethod
        def delay(stage_id):
            raise RuntimeError("broker down")

    for stage_type in ("collection", "parsing", "storage"):
        monkeypatch.setitem(workflow._STAGE_TASKS, stage_type, _FailTask)


@pytest.mark.django_db
def test_requires_auth():
    """任务能触发设备采集，不能匿名可写（项目的 DEFAULT_PERMISSION_CLASSES 是 IsAuthenticated）"""
    assert APIClient().get(TASKS_URL).status_code in (401, 403)


@pytest.mark.django_db
def test_create_task_dispatches_collection_stage(client, device, eager_celery):
    """POST 建任务即投递采集阶段。

    响应里的 Task 是**投递前**建的那个实例，状态必然是 ``running``——异步语义下这才是
    对的（真实链路的最终状态要看详请接口）。投递是否真的发生，用数据库里的阶段数验证。
    """
    DeviceConnection.objects.create(device=device, enabled=True, address="10.0.0.1")

    resp = client.post(TASKS_URL, {"device": device.pk, "task_type": "collect_config"}, format="json")

    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["device"] == device.pk
    assert body["device_hostname"] == device.hostname
    assert body["task_type_display"] == "采集配置"
    assert body["status"] == "running"
    assert sorted(stage["stage_type"] for stage in body["stages"]) == ["collection", "parsing", "storage"]

    assert Task.objects.count() == 1
    assert Stage.objects.filter(task_id=body["id"]).count() == 3
    assert Stage.objects.filter(task_id=body["id"], stage_type="collection").exists()


@pytest.mark.django_db
def test_create_task_returns_503_when_dispatch_fails(client, device, monkeypatch):
    """broker 不可达：返回 503，并且任务要落成 failed（不能挂在「运行中」）"""
    _no_dispatch(monkeypatch)

    resp = client.post(TASKS_URL, {"device": device.pk, "task_type": "collect_config"}, format="json")

    assert resp.status_code == 503
    assert "创建任务失败" in resp.json()["error"]

    task = Task.objects.get()
    assert task.status == "failed"
    assert "broker down" in task.error_message


@pytest.mark.django_db
def test_list_filters_by_device_status_and_type(client, device):
    other = Device.objects.create(hostname="_t_task_dev2", device_type="switch")
    Task.objects.create(task_type="collect_config", device=device, status="running")
    Task.objects.create(task_type="collect_config", device=device, status="success")
    Task.objects.create(task_type="backup_config", device=other, status="success")

    assert client.get(TASKS_URL, {"device": device.pk}).json()["count"] == 2
    assert client.get(TASKS_URL, {"status": "success"}).json()["count"] == 2
    assert client.get(TASKS_URL, {"device": device.pk, "status": "success"}).json()["count"] == 1
    assert client.get(TASKS_URL, {"task_type": "backup_config"}).json()["count"] == 1
    assert client.get(TASKS_URL, {"search": "_t_task_dev2"}).json()["count"] == 1


@pytest.mark.django_db
def test_detail_returns_stages(client, device):
    task = Task.objects.create(task_type="collect_config", device=device, status="failed")
    Stage.objects.create(task=task, stage_type="collection", status="failed", error_message="连接超时")

    body = client.get(f"{TASKS_URL}{task.pk}/").json()

    assert body["task_type_display"] == "采集配置"
    assert len(body["stages"]) == 1
    assert body["stages"][0]["error_message"] == "连接超时"


@pytest.mark.django_db
def test_cancel_running_task(client, device):
    task = Task.objects.create(task_type="collect_config", device=device, status="running")

    resp = client.post(f"{TASKS_URL}{task.pk}/cancel/")

    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    task.refresh_from_db()
    assert task.completed_at is not None


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["success", "failed", "cancelled"])
def test_cancel_rejects_finished_task(client, device, status):
    task = Task.objects.create(task_type="collect_config", device=device, status=status)

    resp = client.post(f"{TASKS_URL}{task.pk}/cancel/")

    assert resp.status_code == 400
    assert "无法取消" in resp.json()["error"]


@pytest.mark.django_db
def test_stages_endpoint_is_read_only_and_filterable(client, device):
    task = Task.objects.create(task_type="collect_config", device=device)
    # 用 update() 落状态：save() 会触发阶段联动信号，把下一个阶段也建出来
    # （非 eager 模式下还会真的往 broker 投递任务）
    collection = Stage.objects.create(task=task, stage_type="collection")
    parsing = Stage.objects.create(task=task, stage_type="parsing")
    Stage.objects.filter(pk=collection.pk).update(status="success")
    Stage.objects.filter(pk=parsing.pk).update(status="running")

    assert client.get("/api/stages/", {"task": task.pk}).json()["count"] == 2
    assert client.get("/api/stages/", {"task": task.pk, "stage_type": "parsing"}).json()["count"] == 1
    assert client.get("/api/stages/", {"task": task.pk, "status": "success"}).json()["count"] == 1
    # 只读：不提供写方法
    assert client.post("/api/stages/", {"task": task.pk, "stage_type": "storage"}, format="json").status_code == 405
