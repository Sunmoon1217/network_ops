"""互联网资产分析链路测试。

覆盖需求中的四个分支：
1. GTM 成员未找到虚拟服务器 → 「未找到」
2. 找到虚拟服务器但没有对应 LTM 虚拟服务器 → 返回虚拟服务器的 IP:端口
3. 虚拟服务器的 IP:端口命中 LTM 虚拟服务器 → 展开池与成员
4. LTM 成员的 IP:端口再次命中下层 LTM 虚拟服务器 → 返回该成员的 IP:端口（级联）
"""

import pytest

from assets.models import (
    Device,
    GtmPool,
    GtmServer,
    GtmVServer,
    GtmWideip,
    LtmPool,
    LtmPoolMember,
    LtmVirtualServer,
)
from ops.api.analysis import analyze_device


def _device(hostname: str, device_type: str = "gslb") -> Device:
    return Device.objects.create(hostname=hostname, device_type=device_type)


def _wideip(device: Device, name: str, pools: list[str]) -> GtmWideip:
    return GtmWideip.objects.create(device=device, name=name, rtype="A", lb_mode="round-robin", pools=pools)


def _gtm_pool(device: Device, name: str, members: list) -> GtmPool:
    return GtmPool.objects.create(device=device, name=name, members=members)


def _gtm_vserver(device: Device, server_name: str, vs_name: str, ip: str, port: str) -> GtmVServer:
    server, _ = GtmServer.objects.get_or_create(device=device, name=server_name)
    return GtmVServer.objects.create(device=device, server=server, name=vs_name, ip_address=ip, port=port)


def _ltm_virtual(device: Device, name: str, ip: str, port: str, pool: str = "") -> LtmVirtualServer:
    return LtmVirtualServer.objects.create(device=device, name=name, vs_address=ip, vs_port=port, pool=pool)


@pytest.mark.django_db
def test_vserver_not_found():
    """GTM 池成员指向的虚拟服务器不存在 → 返回「未找到」"""
    gslb = _device("ia-gslb")
    _wideip(gslb, "www.example.com", ["pool_web"])
    _gtm_pool(gslb, "pool_web", [{"server_name": "s1", "vs_name": "vs1"}])

    member = analyze_device(gslb)["wideips"][0]["pools"][0]["members"][0]

    assert member["status"] == "vserver_not_found"
    assert member["message"] == "未找到"
    assert member["vserver"] is None


@pytest.mark.django_db
def test_ltm_not_found_returns_vserver_ip_port():
    """找到虚拟服务器但没有对应 LTM 虚拟服务器 → 返回虚拟服务器的 IP:端口"""
    gslb = _device("ia-gslb")
    _wideip(gslb, "www.example.com", ["pool_web"])
    _gtm_pool(gslb, "pool_web", [{"server_name": "s1", "vs_name": "vs1"}])
    _gtm_vserver(gslb, "s1", "vs1", "10.1.1.1", "80")

    member = analyze_device(gslb)["wideips"][0]["pools"][0]["members"][0]

    assert member["status"] == "ltm_not_found"
    assert member["vserver"]["ip_address"] == "10.1.1.1"
    assert member["fallback_ip_port"] == "10.1.1.1:80"
    assert member["ltm"] is None


@pytest.mark.django_db
def test_resolved_to_ltm_pool_members():
    """虚拟服务器的 IP:端口命中 LTM 虚拟服务器 → 展开池与成员"""
    gslb = _device("ia-gslb")
    ltm = _device("ia-ltm")
    _wideip(gslb, "www.example.com", ["pool_web"])
    _gtm_pool(gslb, "pool_web", [{"server_name": "s1", "vs_name": "vs1", "member_status": "enabled"}])
    _gtm_vserver(gslb, "s1", "vs1", "10.1.1.1", "80")
    LtmPool.objects.create(device=ltm, name="ltm_pool", mode="round-robin")
    _ltm_virtual(ltm, "vs_web", "10.1.1.1", "80", pool="ltm_pool")
    LtmPoolMember.objects.create(pool_name="ltm_pool", name="m1", address="10.2.2.2", port="8080")

    member = analyze_device(gslb)["wideips"][0]["pools"][0]["members"][0]

    assert member["status"] == "resolved"
    ltm_node = member["ltm"]
    assert ltm_node["device"] == "ia-ltm"
    assert ltm_node["pool"] == "ltm_pool"
    assert ltm_node["pool_found"] is True
    assert ltm_node["members"][0]["ip_port"] == "10.2.2.2:8080"
    assert ltm_node["members"][0]["nested"] is None


@pytest.mark.django_db
def test_nested_cascade_returns_member_ip_port():
    """LTM 成员的 IP:端口再次命中下层 LTM 虚拟服务器 → 返回该成员的 IP:端口"""
    gslb = _device("ia-gslb")
    ltm1 = _device("ia-ltm1")
    ltm2 = _device("ia-ltm2")
    _wideip(gslb, "www.example.com", ["pool_web"])
    _gtm_pool(gslb, "pool_web", [{"server_name": "s1", "vs_name": "vs1"}])
    _gtm_vserver(gslb, "s1", "vs1", "10.1.1.1", "80")

    LtmPool.objects.create(device=ltm1, name="pool1", mode="round-robin")
    _ltm_virtual(ltm1, "vs1", "10.1.1.1", "80", pool="pool1")
    LtmPoolMember.objects.create(pool_name="pool1", name="m1", address="10.2.2.2", port="8080")

    # 下层 LTM：地址端口正好等于上一层的池成员
    LtmPool.objects.create(device=ltm2, name="pool2", mode="round-robin")
    _ltm_virtual(ltm2, "vs2", "10.2.2.2", "8080", pool="pool2")
    LtmPoolMember.objects.create(pool_name="pool2", name="m2", address="10.3.3.3", port="9090")

    member = analyze_device(gslb)["wideips"][0]["pools"][0]["members"][0]

    assert member["status"] == "resolved"
    nested_member = member["ltm"]["members"][0]
    assert nested_member["matched_ip_port"] == "10.2.2.2:8080"
    assert nested_member["nested"]["device"] == "ia-ltm2"
    assert nested_member["nested"]["members"][0]["address"] == "10.3.3.3"


@pytest.mark.django_db
def test_pool_not_found_is_reported():
    """WideIP 引用的池在 GtmPool 中没有记录 → found=false"""
    gslb = _device("ia-gslb")
    _wideip(gslb, "www.example.com", ["pool_missing"])

    pool_node = analyze_device(gslb)["wideips"][0]["pools"][0]

    assert pool_node["found"] is False
    assert pool_node["members"] == []
