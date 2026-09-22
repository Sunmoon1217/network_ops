"""互联网资产分析链路测试。

覆盖需求中的四个分支：
1. GTM 成员未找到虚拟服务器 → 「未找到」
2. 找到虚拟服务器但没有对应 LTM 虚拟服务器 → 返回虚拟服务器的 IP:端口
3. 虚拟服务器的 IP:端口命中 LTM 虚拟服务器 → 展开池与成员
4. LTM 成员的 IP:端口再次命中下层 LTM 虚拟服务器 → 返回该成员的 IP:端口（级联）
"""

import pytest

from analysis.api.analysis import analyze_device
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
    assert member["fallback_ip_port"] == "10.1.1.1#80"
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
    LtmPoolMember.objects.create(device=ltm, pool_name="ltm_pool", name="m1", address="10.2.2.2", port="8080")

    member = analyze_device(gslb)["wideips"][0]["pools"][0]["members"][0]

    assert member["status"] == "resolved"
    ltm_node = member["ltm"]
    assert ltm_node["device"] == "ia-ltm"
    assert ltm_node["pool"] == "ltm_pool"
    assert ltm_node["pool_found"] is True
    assert ltm_node["members"][0]["ip_port"] == "10.2.2.2#8080"
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
    LtmPoolMember.objects.create(device=ltm1, pool_name="pool1", name="m1", address="10.2.2.2", port="8080")

    # 下层 LTM：地址端口正好等于上一层的池成员
    LtmPool.objects.create(device=ltm2, name="pool2", mode="round-robin")
    _ltm_virtual(ltm2, "vs2", "10.2.2.2", "8080", pool="pool2")
    LtmPoolMember.objects.create(device=ltm2, pool_name="pool2", name="m2", address="10.3.3.3", port="9090")

    member = analyze_device(gslb)["wideips"][0]["pools"][0]["members"][0]

    assert member["status"] == "resolved"
    nested_member = member["ltm"]["members"][0]
    assert nested_member["matched_ip_port"] == "10.2.2.2#8080"
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


# ---------- 池成员 key 的兼容性 ----------


def test_parse_member_entry_accepts_template_shape():
    """模板解析产出的形态"""
    from analysis.api.analysis import _parse_member_entry

    assert _parse_member_entry({"server_name": "s1", "vs_name": "vs1"})[:2] == ("s1", "vs1")


def test_parse_member_entry_accepts_saver_shape():
    """GtmPoolSaver 入库后 key 改名为 server / vserver，分析侧必须认。

    这条曾经不成立：Saver 写 "vserver"，分析侧只读 "vs_name" / "virtual_server"，
    于是 vs_name 恒为空，find_vserver 找不到 GTM 虚拟服务器，整条链路在第一步
    就被判成「GTM 虚拟服务器未找到」（member_ref 也会退化成 "s1:"）。
    """
    from analysis.api.analysis import _parse_member_entry

    assert _parse_member_entry({"server": "s1", "vserver": "vs1"})[:2] == ("s1", "vs1")


def test_parse_member_entry_falls_back_to_name():
    """缺哪一半就用 "server:vs" 形式的 name 补哪一半"""
    from analysis.api.analysis import _parse_member_entry

    assert _parse_member_entry({"server": "s1", "name": "s1:vs1"})[:2] == ("s1", "vs1")
    assert _parse_member_entry({"name": "s1:vs1"})[:2] == ("s1", "vs1")
    assert _parse_member_entry("s1:vs1")[:2] == ("s1", "vs1")


@pytest.mark.django_db
def test_members_written_by_saver_are_resolvable():
    """端到端：经 GtmPoolSaver 入库的池成员，分析时必须能解析到 GTM 虚拟服务器。"""
    from ops.savers.lb import GtmPoolSaver

    gslb = _device("ia-saver-keys")
    server = GtmServer.objects.create(device=gslb, name="s1")
    GtmVServer.objects.create(device=gslb, server=server, name="vs1", ip_address="10.1.1.1", port="80")
    _wideip(gslb, "www.example.com", ["pool_web"])

    GtmPoolSaver().save(
        gslb,
        {"pools": {"pool_name": "pool_web", "members": [{"server_name": "/Common/s1", "vs_name": "vs1"}]}},
    )

    # 库里存的是 Saver 口径的 key
    stored = GtmPool.objects.get(device=gslb).members[0]
    assert {"server", "vserver"} <= set(stored)

    member = analyze_device(gslb)["wideips"][0]["pools"][0]["members"][0]
    assert member["member_ref"] == "s1:vs1"
    assert member["status"] == "ltm_not_found"  # 只造了 GTM 侧，止步于第二步
    assert member["vserver"]["name"] == "vs1"


# ---------- IPv6 链路 ----------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "ltm_address",
    [
        "2001:db8::1",  # 与 GTM 侧写法一致
        "2001:DB8::1",  # 大写
        "2001:0db8:0000:0000:0000:0000:0000:0001",  # 前导零 + 未压缩
    ],
)
def test_ipv6_chain_resolves_regardless_of_address_writing(ltm_address):
    """IPv6 地址的大小写 / 前导零 / 压缩写法不同，不应影响 LLB 匹配。

    GtmVServer.ip_address 是 GenericIPAddressField（Django 规范化），而
    LtmVirtualServer.vs_address 是 CharField（原样存），按字符串直接比较会漏。
    """
    gslb = _device("ia-v6")
    GtmWideip.objects.create(device=gslb, name="v6.example.com", rtype="AAAA", pools=["pool_v6"])
    GtmPool.objects.create(device=gslb, name="pool_v6", members=[{"server": "s1", "vserver": "vs_v6"}])
    server = GtmServer.objects.create(device=gslb, name="s1")
    GtmVServer.objects.create(device=gslb, server=server, name="vs_v6", ip_address="2001:db8::1", port="80")

    ltm = _device("ia-v6-ltm", "slb")
    LtmVirtualServer.objects.create(device=ltm, name="vs_v6", vs_address=ltm_address, vs_port="80")

    member = analyze_device(gslb)["wideips"][0]["pools"][0]["members"][0]

    assert member["status"] == "resolved"
    assert member["ltm"]["vs_address"] == ltm_address


# ---------- 池成员的设备作用域 ----------


@pytest.mark.django_db
def test_same_pool_name_on_other_device_is_not_mixed_in():
    """另一台设备上的同名池成员不能被算进来。

    旧实现按 ``pool_name`` 全局索引成员，两台设备都有 ``shared_pool`` 时，
    A 的虚拟服务器会把 B 的成员一起展开。
    """
    gslb = _device("ia-scope-gslb")
    _wideip(gslb, "www.example.com", ["pool_web"])
    _gtm_pool(gslb, "pool_web", [{"server_name": "s1", "vs_name": "vs1"}])
    _gtm_vserver(gslb, "s1", "vs1", "10.1.1.1", "80")

    ltm_a = _device("ia-scope-ltm-a", "slb")
    LtmPool.objects.create(device=ltm_a, name="shared_pool", mode="round-robin")
    _ltm_virtual(ltm_a, "vs_web", "10.1.1.1", "80", pool="shared_pool")
    LtmPoolMember.objects.create(device=ltm_a, pool_name="shared_pool", name="from_a", address="10.2.2.2", port="80")

    ltm_b = _device("ia-scope-ltm-b", "slb")
    LtmPool.objects.create(device=ltm_b, name="shared_pool", mode="round-robin")
    LtmPoolMember.objects.create(device=ltm_b, pool_name="shared_pool", name="from_b", address="10.9.9.9", port="80")

    ltm_node = analyze_device(gslb)["wideips"][0]["pools"][0]["members"][0]["ltm"]

    assert ltm_node["device"] == "ia-scope-ltm-a"
    assert [m["name"] for m in ltm_node["members"]] == ["from_a"]


@pytest.mark.django_db
def test_pool_found_is_scoped_to_device():
    """``pool_found`` 也要按设备判断：池只存在于别的设备上时不能算找到"""
    gslb = _device("ia-pf-gslb")
    _wideip(gslb, "www.example.com", ["pool_web"])
    _gtm_pool(gslb, "pool_web", [{"server_name": "s1", "vs_name": "vs1"}])
    _gtm_vserver(gslb, "s1", "vs1", "10.1.1.1", "80")

    ltm_a = _device("ia-pf-ltm-a", "slb")
    _ltm_virtual(ltm_a, "vs_web", "10.1.1.1", "80", pool="only_on_b")

    ltm_b = _device("ia-pf-ltm-b", "slb")
    LtmPool.objects.create(device=ltm_b, name="only_on_b", mode="round-robin")

    ltm_node = analyze_device(gslb)["wideips"][0]["pools"][0]["members"][0]["ltm"]

    assert ltm_node["pool"] == "only_on_b"
    assert ltm_node["pool_found"] is False
    assert ltm_node["members"] == []


@pytest.mark.django_db
def test_f5_ltm_parses_ipv4_and_ipv6_destination():
    """F5 的 IPv6 destination 用点号分隔端口，模板必须区分两种写法"""
    from ops.parsers.factory import ParserFactory

    config = """ltm virtual /Common/vs_v4 {
    destination /Common/10.0.0.1:443
    ip-protocol tcp
}
ltm virtual /Common/vs_v6 {
    destination /Common/2001:db8::1.80
    ip-protocol tcp
}
"""
    parsed = ParserFactory.get_parser_by_keys("F5", "slb").parse(config)["virtuals"]

    by_name = {item["name"]: item for item in parsed}
    assert (by_name["/Common/vs_v4"]["vs_address"], by_name["/Common/vs_v4"]["vs_port"]) == ("10.0.0.1", "443")
    # 不区分的话这里会是 "2001:db8:" + "1.80"
    assert (by_name["/Common/vs_v6"]["vs_address"], by_name["/Common/vs_v6"]["vs_port"]) == ("2001:db8::1", "80")
