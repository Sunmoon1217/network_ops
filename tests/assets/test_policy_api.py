"""访问策略列表接口的跨表展示测试。

`PolicySerializer` 把三个 M2M（源/目的 AddressBook、服务 Service）预格式化成
`*_display` 字符串数组，`PolicyViewSet` 用 `prefetch_related` 一次取回——
本文件同时守展示内容与「不逐行查询」（N+1）两件事。
"""

import pytest
from rest_framework.test import APIClient

from assets.models import AddressBook, Device, Policy, Service

URL = "/api/assets/policies/"


def _device(hostname: str) -> Device:
    return Device.objects.create(hostname=hostname, device_type="firewall")


def _policy_with_refs(device: Device) -> Policy:
    source = AddressBook.objects.create(
        device=device, name="office", address_type="subnet", ip_address="10.0.0.0", ip_netmask=24
    )
    destination = AddressBook.objects.create(device=device, name="srv", address_type="host", ip_address="10.0.0.8")
    service = Service.objects.create(device=device, name="HTTP", protocol="tcp", port="80")
    policy = Policy.objects.create(
        device=device, policy_id="1", order=1, name="allow-office", action="allow", enabled=True, log=True
    )
    policy.source_addresses.set([source])
    policy.destination_addresses.set([destination])
    policy.services.set([service])
    return policy


@pytest.mark.django_db
def test_list_returns_display_strings_for_cross_table_fields():
    """源/目的地址与端口以格式化字符串返回，前端不必再解析地址簿结构"""
    device = _device("api-pol-a")
    _policy_with_refs(device)

    row = APIClient().get(URL).json()["results"][0]

    assert row["device_hostname"] == "api-pol-a"
    assert row["policy_id"] == "1"
    assert row["action"] == "allow"
    assert row["enabled"] is True
    assert row["log"] is True
    assert row["source_addresses_display"] == ["office(10.0.0.0/24)"]
    # host 条目也带名字（M2M 按 AddressBook Meta 的 name 排序返回）
    assert row["destination_addresses_display"] == ["srv(10.0.0.8)"]
    assert row["services_display"] == ["tcp/80"]
    # M2M 主键字段仍在（编辑表单要写回）
    assert len(row["source_addresses"]) == 1


@pytest.mark.django_db
def test_empty_match_conditions_display_as_any():
    """没有关联地址/服务时 display 为空数组（前端约定显示 any）"""
    device = _device("api-pol-empty")
    Policy.objects.create(device=device, policy_id="9", order=1, name="any-any", action="deny")

    row = APIClient().get(URL).json()["results"][0]

    assert row["source_addresses_display"] == []
    assert row["destination_addresses_display"] == []
    assert row["services_display"] == []


@pytest.mark.django_db
def test_list_does_not_query_per_row(django_assert_num_queries):
    """5 条策略 × 各 3 个 M2M，查询数应与 1 条时相同（prefetch 而非 N+1）"""
    device = _device("api-pol-n1")
    for index in range(5):
        source = AddressBook.objects.create(
            device=device, name=f"src{index}", address_type="host", ip_address=f"10.0.{index}.1"
        )
        policy = Policy.objects.create(
            device=device, policy_id=str(index), order=index, name=f"rule-{index}", action="allow"
        )
        policy.source_addresses.set([source])

    with django_assert_num_queries(5):
        rows = APIClient().get(URL).json()["results"]
    assert len(rows) == 5


@pytest.mark.django_db
def test_range_and_subnet_entries_are_formatted_by_type():
    """range 起止、subnet 前缀、addressbook 引用各自的展示格式"""
    device = _device("api-pol-fmt")
    address = AddressBook.objects.create(
        device=device, name="pool", address_type="range", ip_start="10.1.1.10", ip_end="10.1.1.20"
    )
    book = AddressBook.objects.create(device=device, name="office", address_type="addressbook")
    port_range = Service.objects.create(device=device, name="WEB", protocol="tcp", port="8000", port2="8010")
    policy = Policy.objects.create(device=device, policy_id="2", order=1, name="fmt", action="deny")
    policy.source_addresses.set([address, book])
    policy.services.set([port_range])

    row = APIClient().get(URL).json()["results"][0]

    # M2M 按 AddressBook Meta 的 name 字母序返回：office 在 pool 之前
    assert row["source_addresses_display"] == ["office", "pool(10.1.1.10-10.1.1.20)"]
    assert row["services_display"] == ["tcp/8000-8010"]
