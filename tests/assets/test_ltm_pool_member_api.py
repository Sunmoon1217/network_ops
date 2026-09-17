"""LTM 池成员 API 测试。

`LtmPoolMember` 继承 `ConfigBase` 后新增了 `device` / `is_active` / `created_at`，
列表接口要能返回 `device_hostname` 与 `port`，并支持按 `device` 过滤 ——
池成员是按「设备 + 池名」定位的，做不到按设备过滤就等于放弃了这次的收窄。
"""

import pytest
from rest_framework.test import APIClient

from assets.models import Device, LtmPoolMember

URL = "/api/assets/ltm-pool-members/"


def _device(hostname: str) -> Device:
    return Device.objects.create(hostname=hostname, device_type="slb")


@pytest.mark.django_db
def test_list_returns_device_hostname_and_port():
    device = _device("api-ltm-a")
    LtmPoolMember.objects.create(device=device, pool_name="pool_web", name="node_a", address="10.0.0.1", port="8080")

    payload = APIClient().get(URL).json()

    assert payload["count"] == 1
    row = payload["results"][0]
    assert row["device"] == device.pk
    assert row["device_hostname"] == "api-ltm-a"
    assert row["pool_name"] == "pool_web"
    assert row["name"] == "node_a"
    assert row["address"] == "10.0.0.1"
    assert row["port"] == "8080"
    assert row["is_active"] is True


@pytest.mark.django_db
def test_list_can_filter_by_device():
    """两台设备各有同名池的成员，按 device 过滤要能分开"""
    dev_a = _device("api-ltm-a")
    dev_b = _device("api-ltm-b")
    LtmPoolMember.objects.create(device=dev_a, pool_name="shared", name="from_a", address="10.0.0.1", port="80")
    LtmPoolMember.objects.create(device=dev_b, pool_name="shared", name="from_b", address="10.0.0.2", port="80")

    payload = APIClient().get(URL, {"device": dev_a.pk}).json()

    assert payload["count"] == 1
    assert payload["results"][0]["name"] == "from_a"


@pytest.mark.django_db
def test_deleting_device_removes_member_from_api():
    """级联删设备后列表里不应再有它的成员"""
    device = _device("api-ltm-gone")
    LtmPoolMember.objects.create(device=device, pool_name="p", name="n", address="10.0.0.1", port="80")

    device.delete()

    assert APIClient().get(URL).json()["count"] == 0
