"""路径追踪回归测试。

覆盖本轮修复的缺陷：
- 同名 VRF（如 default）跨设备不再被误判为环路
- Interface.vrf 是外键，必须取 .name，不能把 Vrf 对象当作 VRF 名继续传递
- 端口解析对非数字 / 范围 / 越界输入不抛异常
- IPv4 子网的路由链跟踪遇到 IPv6 路由不抛 TypeError
- Subnet.network / Route.destination 能容纳完整 IPv6 CIDR
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from assets.models import AddressBook, DataCenter, Device, Interface, Policy, Route, SecurityZone, Subnet, Vrf
from ops import path_tracer as pt


class _FakeQS:
    """模拟 related manager 的 .all()"""

    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _FakeService:
    def __init__(self, port="", port2=""):
        self.port = port
        self.port2 = port2


@pytest.mark.parametrize(
    ("port", "svc_port", "svc_port2", "expected"),
    [
        ("80", "80", "", True),
        ("443", "80", "443", True),
        ("8443", "8000-9000", "", True),
        ("8080", "80,443,8080", "", True),
        ("abc", "80", "", False),  # 请求端口非法：不得抛异常
        ("80", "any", "", False),  # 服务端口写成非数字：不得抛异常
        ("80", "http", "", False),
        ("80", "80-", "", False),
        ("99999", "80", "", False),  # 越界端口
        ("0", "", "", False),
    ],
)
def test_match_service_is_defensive(port, svc_port, svc_port2, expected):
    service = _FakeService(svc_port, svc_port2)
    assert pt._match_service(port, _FakeQS([service])) is expected


def _build_two_device_chain(*, with_vrf_on_recv: bool) -> None:
    """构造 A(default) --10.0.0.0/24-- B(VRF-DST) 的两跳拓扑"""
    device_a = Device.objects.create(hostname="pt-test-a", device_type="switch")
    device_b = Device.objects.create(hostname="pt-test-b", device_type="switch")
    vrf_a = Vrf.objects.create(device=device_a, name="default")
    vrf_b = Vrf.objects.create(device=device_b, name="VRF-DST")
    Interface.objects.create(device=device_a, interface="Gi0/1", ip_address="10.0.0.1")
    Interface.objects.create(
        device=device_b, interface="Gi0/1", ip_address="10.0.0.2", vrf=vrf_b if with_vrf_on_recv else None
    )
    Route.objects.create(vrf=vrf_a, destination="10.9.9.0/24", nexthop="10.0.0.2", protocol="static")
    Subnet.objects.create(network="10.0.0.0/24", gateway="10.0.0.1")
    Subnet.objects.create(network="10.9.9.0/24", gateway="10.0.0.2")


@pytest.mark.django_db
def test_same_vrf_multi_hop_is_not_reported_as_loop():
    """A(default) -> B(default) 必须走满两跳；修复前第 2 跳会被误判为 VRF 环路"""
    _build_two_device_chain(with_vrf_on_recv=False)

    result = pt.trace_path("10.0.0.100", "10.9.9.5", "")

    assert result.error == ""
    assert [h.device_name for h in result.hops] == ["pt-test-a", "pt-test-b"]
    assert [h.vrf for h in result.hops] == ["default", "default"]


@pytest.mark.django_db
def test_receiving_interface_vrf_is_a_name_string():
    """接收接口配了 VRF 时 hop.vrf 必须是名字；修复前是 Vrf 对象，导致后续查不到 VRF"""
    _build_two_device_chain(with_vrf_on_recv=True)

    result = pt.trace_path("10.0.0.100", "10.9.9.5", "")

    assert all(isinstance(h.vrf, str) for h in result.hops), [h.vrf for h in result.hops]
    assert result.hops[-1].vrf == "VRF-DST"


@pytest.mark.django_db
def test_routing_table_tracking_ignores_other_ip_version():
    """路由链跟踪同时存在 IPv4/IPv6 路由时不得抛 TypeError"""
    device = Device.objects.create(hostname="pt-test-v6", device_type="switch")
    vrf = Vrf.objects.create(device=device, name="default")
    datacenter = DataCenter.objects.create(name="pt-test-dc")
    zone = SecurityZone.objects.create(name="pt-test-zone")
    Subnet.objects.create(network="10.1.0.0/16", datacenter=datacenter, security_zone=zone, gateway="10.1.0.1")
    Interface.objects.create(device=device, interface="Gi0/1", ip_address="10.1.0.1")
    Route.objects.create(vrf=vrf, destination="2001:db8::/32", nexthop="10.1.0.2", protocol="static")
    Route.objects.create(vrf=vrf, destination="10.1.0.0/16", nexthop="10.1.0.2", protocol="static")

    subnet = pt._find_subnet_for_ip("10.1.0.5")
    assert subnet is not None
    assert pt._find_vrf_from_routing_table("10.1.0.5", subnet) == "default"


@pytest.mark.django_db
def test_ipv6_cidr_fits_model_fields():
    """模型字段放宽后，43 字符的完整 IPv6 CIDR 必须能入库"""
    long_cidr = "2001:0db8:85a3:0000:0000:8a2e:0370:7334/128"
    assert len(long_cidr) == 43

    subnet = Subnet.objects.create(network=long_cidr)
    device = Device.objects.create(hostname="pt-test-len", device_type="switch")
    vrf = Vrf.objects.create(device=device, name="default")
    route = Route.objects.create(vrf=vrf, destination=long_cidr, protocol="static")

    assert subnet.network == long_cidr
    assert route.destination == long_cidr


def _build_addressbook_chain(device, name_prefix: str, depth: int, leaf_ip: str) -> AddressBook:
    """构造 depth 层嵌套的地址簿树，叶子放一个 host，返回最外层地址簿"""
    parent = None
    for level in range(depth):
        parent = AddressBook.objects.create(
            name=f"{name_prefix}-lvl{level}", address_type="addressbook", parent=parent, device=device
        )
    AddressBook.objects.create(
        name=f"{name_prefix}-leaf", address_type="host", ip_address=leaf_ip, parent=parent, device=device
    )
    return parent


def _build_policy(device, policy_id: str, order: int, source_book: AddressBook) -> Policy:
    policy = Policy.objects.create(
        device=device, policy_id=policy_id, order=order, name=f"policy-{policy_id}", action="deny", enabled=True
    )
    policy.source_addresses.add(source_book)
    return policy


@pytest.mark.django_db
def test_policy_match_query_count_is_independent_of_tree_depth():
    """策略匹配的 SQL 次数不得随地址簿树深度增长（防 N+1 回归）"""
    shallow_device = Device.objects.create(hostname="pt-sql-shallow", device_type="firewall")
    deep_device = Device.objects.create(hostname="pt-sql-deep", device_type="firewall")
    _build_policy(
        shallow_device, "P-SHALLOW", 1, _build_addressbook_chain(shallow_device, "pt-shallow", 1, "192.0.2.1")
    )
    _build_policy(deep_device, "P-DEEP", 1, _build_addressbook_chain(deep_device, "pt-deep", 8, "192.0.2.1"))

    def count_queries(device) -> int:
        index = pt._load_addressbook_index()  # 索引加载不计入匹配过程
        with CaptureQueriesContext(connection) as ctx:
            pt._match_policy("192.0.2.1", "198.51.100.1", "80", device, index)
        return len(ctx)

    shallow_queries = count_queries(shallow_device)
    deep_queries = count_queries(deep_device)

    assert shallow_queries == deep_queries, (shallow_queries, deep_queries)
    # 策略查询 + source_addresses / destination_addresses / services 三次预取
    assert deep_queries <= 4


@pytest.mark.django_db
def test_deep_addressbook_tree_still_matches():
    """索引化后深层地址簿仍能正确命中，且不误命中"""
    device = Device.objects.create(hostname="pt-deep-match", device_type="firewall")
    book = _build_addressbook_chain(device, "pt-deepmatch", 8, "192.0.2.55")
    _build_policy(device, "P-DEEP-MATCH", 1, book)

    index = pt._load_addressbook_index()
    hit = pt._match_policy("192.0.2.55", "198.51.100.1", "80", device, index)
    miss = pt._match_policy("203.0.113.9", "198.51.100.1", "80", device, index)

    assert hit is not None
    assert hit["action"] == "deny"
    assert miss is None
