"""防火墙主备合并接口（``/api/analysis/firewall-groups/*``）测试。

覆盖：① 策略按 policy_id 合并、NAT 按 order 合并；② 内容冲突取主机名第一台并标注；
③ 单机/堆叠不合并；④ 组/设备/动作/类型过滤、搜索、排序、分页；⑤ facets。
"""

import pytest
from rest_framework.test import APIClient

from assets.models import AddressBook, Device, DeviceGroup, DeviceGroupMember, NatRule, Policy, Service

POLICIES = "/api/analysis/firewall-groups/policies/"
NAT_RULES = "/api/analysis/firewall-groups/nat-rules/"
FACETS = "/api/analysis/firewall-groups/facets/"


@pytest.fixture
def api():
    return APIClient()


def _device(hostname: str) -> Device:
    return Device.objects.create(hostname=hostname, device_type="firewall")


def _group(name: str, group_type: str, devices: list[Device]) -> DeviceGroup:
    group = DeviceGroup.objects.create(name=name, group_type=group_type)
    for device in devices:
        DeviceGroupMember.objects.create(group=group, device=device)
    return group


def _address(device, name: str, ip: str) -> AddressBook:
    return AddressBook.objects.create(device=device, name=name, address_type="host", ip_address=ip)


def _service(device, name: str, port: str, protocol: str = "tcp") -> Service:
    return Service.objects.create(device=device, name=name, protocol=protocol, port=port)


def _policy(device, policy_id="100", order=10, name="allow-web", action="allow", sources=None, services=None):
    policy = Policy.objects.create(
        device=device, policy_id=policy_id, order=order, name=name, action=action, enabled=True
    )
    if sources:
        policy.source_addresses.set(sources)
    if services:
        policy.services.set(services)
    return policy


def _nat(device, order=1, name="snat-web", nat_type="snat", translated_source=None):
    return NatRule.objects.create(
        device=device, order=order, name=name, nat_type=nat_type, enabled=True, translated_source=translated_source
    )


@pytest.mark.django_db
def test_ha_policies_and_nat_merge_with_joined_device(api):
    """主备两台防火墙的同一策略 / NAT 合并成一行，device 逗号拼接、展示串格式化。"""
    a, b = _device("fw-a"), _device("fw-b")
    _group("fw-pair", "ha", [a, b])
    for device in (a, b):
        source = _address(device, "office", "10.0.0.0")
        web = _service(device, "web", "80")
        _policy(device, sources=[source], services=[web])
        _nat(device, translated_source=_address(device, "pub", "1.1.1.1"))

    policy = api.get(POLICIES).data["results"][0]
    assert policy["group_name"] == "fw-pair"
    assert policy["device"] == "fw-a,fw-b"
    assert policy["policy_id"] == "100"
    assert policy["source_addresses_display"] == ["office(10.0.0.0)"]
    assert policy["services_display"] == ["tcp/80"]
    assert policy["inconsistent"] is False

    nat = api.get(NAT_RULES).data["results"][0]
    assert nat["device"] == "fw-a,fw-b"
    assert nat["translated_source"] == "pub"
    assert nat["inconsistent"] is False


@pytest.mark.django_db
def test_policy_id_conflict_takes_first_hostname_and_flags(api):
    """同 policy_id 在两台上动作/地址不同：取主机名第一台，逐字段标注（不并集）。"""
    a, b = _device("fw-a"), _device("fw-b")
    _group("fw-pair", "ha", [a, b])
    # b 先建，验证最终取的是主机名第一台而不是插入顺序
    _policy(b, policy_id="100", order=10, name="allow-web", action="deny")
    _policy(a, policy_id="100", order=10, name="allow-web", action="allow")
    # 源地址内容不同 → 冲突字段 source_addresses
    Policy.objects.get(device=b, policy_id="100").source_addresses.set([_address(b, "office", "10.9.0.0")])
    Policy.objects.get(device=a, policy_id="100").source_addresses.set([_address(a, "office", "10.0.0.0")])

    row = api.get(POLICIES).data["results"][0]
    assert row["action"] == "allow"  # 主机名第一台 fw-a
    assert row["inconsistent"] is True
    assert set(row["conflict_fields"]) == {"action", "source_addresses"}


@pytest.mark.django_db
def test_single_and_stack_groups_are_not_merged(api):
    """单机 / 堆叠组不参与合并：成员各自成为单机组。"""
    a, b = _device("fw-a"), _device("fw-b")
    _group("fw-stack", "stack", [a, b])
    for device in (a, b):
        _policy(device)
        _nat(device)

    rows = api.get(POLICIES).data["results"]
    assert [(row["group_name"], row["device"]) for row in rows] == [("fw-a", "fw-a"), ("fw-b", "fw-b")]


@pytest.mark.django_db
def test_filters_search_ordering_and_facets(api):
    device = _device("fw-a")
    _policy(device, policy_id="100", order=10, name="allow-web", action="allow")
    _policy(device, policy_id="200", order=20, name="deny-db", action="deny")
    _nat(device, order=1, name="snat-a", nat_type="snat")
    _nat(device, order=2, name="dnat-b", nat_type="dnat")

    assert [row["policy_id"] for row in api.get(POLICIES, {"action": "deny"}).data["results"]] == ["200"]
    assert [row["policy_id"] for row in api.get(POLICIES, {"search": "allow-web"}).data["results"]] == ["100"]
    assert [row["name"] for row in api.get(NAT_RULES, {"nat_type": "dnat"}).data["results"]] == ["dnat-b"]
    assert [row["policy_id"] for row in api.get(POLICIES, {"ordering": "-order"}).data["results"]] == ["200", "100"]

    payload = api.get(POLICIES, {"page_size": 1}).data
    assert payload["count"] == 2 and len(payload["results"]) == 1 and payload["next"]

    facets = api.get(FACETS).data
    assert [group["name"] for group in facets["groups"]] == ["fw-a"]
    assert facets["actions"] == ["allow", "deny"]
    assert facets["nat_types"] == ["dnat", "snat"]


@pytest.mark.django_db
def test_group_and_device_filter_scope_to_whole_group(api):
    a, b, other = _device("fw-a"), _device("fw-b"), _device("fw-other")
    group = _group("fw-pair", "failover", [a, b])
    for device in (a, b, other):
        _policy(device)

    for params in ({"group": f"group-{group.pk}"}, {"group": "fw-pair"}, {"device": b.pk}):
        results = api.get(POLICIES, params).data["results"]
        assert [row["device"] for row in results] == ["fw-a,fw-b"], params

    assert [row["device"] for row in api.get(POLICIES, {"device": other.pk}).data["results"]] == ["fw-other"]
    assert api.get(POLICIES, {"device": "abc"}).data["count"] == 0
