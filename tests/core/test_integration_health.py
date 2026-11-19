"""外部连接健康状态：探活落库 + 跨进程只读接口。

实例是进程内的，admin / MCP 看不到采集进程持有什么；这里锁住三件事：

1. `probe_all` 逐 provider 探活，成功记 ``ok``、异常记 ``down`` + 错误，且按
   ``(system, instance)`` **upsert**（同一实例只有一行，不堆积历史）；
2. API 返回「已注册实例 ∪ 健康行」，没探过的是 ``unknown``，不能伪装成健康；
3. beat 调度的任务名与 celery 装饰器同名（改名不同步会静默不执行）。
"""

from typing import Any, cast

import pytest
from django.conf import settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import IntegrationHealth, User

INTEGRATIONS_URL = "/api/core/integrations/"


class _FakeProvider:
    def __init__(self, *, system: str = "fake", instance: str = "default", error: Exception | None = None) -> None:
        self.system = system
        self.instance = instance
        self.error = error
        self.acquired = 0
        self.released = 0

    async def acquire(self) -> dict[str, str]:
        self.acquired += 1
        if self.error is not None:
            raise self.error
        return {"client": "fake"}

    async def release(self) -> None:
        self.released += 1

    def describe(self) -> dict[str, object]:
        return {
            "system": self.system,
            "instance": self.instance,
            "base_url": f"http://{self.system}.example.com",
            "configured": True,
        }


@pytest.fixture
def registry(monkeypatch):
    """空注册表：不碰应用启动时真实注册的 Zabbix。"""
    from core.integrations import registry as registry_module

    monkeypatch.setattr(registry_module, "_providers", {})
    return registry_module


@pytest.fixture
def operator(db):
    return User.objects.create_user(username="_t_int_health", password="x", role="operator")


def test_probe_all_records_ok_and_releases(registry, db):
    from core.integrations import register_provider
    from core.integrations.health import probe_all

    provider = _FakeProvider()
    register_provider(provider)

    assert probe_all() == 1

    row = IntegrationHealth.objects.get(system="fake", instance="default")
    assert row.status == "ok"
    assert row.error == ""
    assert row.checked_at is not None
    # 探活拿到实例后立刻释放：beat 进程不该长期持有 session
    assert provider.acquired == 1
    assert provider.released == 1


def test_probe_all_records_down_with_error(registry, db):
    from core.integrations import register_provider
    from core.integrations.health import probe_all

    register_provider(_FakeProvider(error=RuntimeError("connect refused")))

    assert probe_all() == 1
    row = IntegrationHealth.objects.get(system="fake", instance="default")
    assert row.status == "down"
    assert "connect refused" in row.error


def test_probe_is_upsert_not_append(registry, db):
    from core.integrations import register_provider
    from core.integrations.health import probe_all

    register_provider(_FakeProvider())
    probe_all()
    first = IntegrationHealth.objects.get(system="fake", instance="default")

    probe_all()

    rows = IntegrationHealth.objects.filter(system="fake", instance="default")
    assert rows.count() == 1
    assert rows.get().pk == first.pk


def test_snapshot_marks_unprobed_as_unknown(registry, db):
    from core.integrations import register_provider
    from core.integrations.health import snapshot

    register_provider(_FakeProvider())
    item = next(i for i in snapshot() if i["system"] == "fake")
    assert item["status"] == "unknown"
    assert item["checked_at"] is None
    assert item["description"]["base_url"] == "http://fake.example.com"


def test_snapshot_keeps_rows_without_local_provider(registry, db):
    """API 进程没注册某域时，库里已有的状态仍要能看见（跨进程差异要暴露，不隐藏）。"""
    from core.integrations.health import snapshot

    IntegrationHealth.objects.create(system="ghost", instance="default", status="down", checked_at=timezone.now(), error="boom")
    item = next(i for i in snapshot() if i["system"] == "ghost")
    assert item["status"] == "down"
    assert item["description"] == {}


def test_api_lists_instances_and_health(registry, operator, db):
    from core.integrations import register_provider

    register_provider(_FakeProvider())
    api = APIClient()
    api.force_authenticate(user=operator)

    resp = api.get(INTEGRATIONS_URL)

    assert resp.status_code == 200
    item = next(i for i in resp.data if i["system"] == "fake")
    assert item["instance"] == "default"
    assert item["status"] == "unknown"
    assert item["description"]["configured"] is True


def test_beat_schedule_matches_task_name():
    entry = settings.CELERY_BEAT_SCHEDULE["integration-health"]
    assert entry["task"] == settings.INTEGRATION_PROBE_TASK

    from core.tasks import probe_integration_health

    # 装饰器 name= 与 beat 的 key 同源（celery 的 task 属性在 stubs 里没有 .name）
    assert cast(Any, probe_integration_health).name == settings.INTEGRATION_PROBE_TASK
