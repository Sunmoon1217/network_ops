"""关联链聚合接口（/api/lb-chain/*）测试。

覆盖三件事：① 整链拼装（VS→池→成员、WideIP→池→GTM虚拟服务器）；
② device 过滤与搜索（含成员地址 / 池名的反查路径）；③ 分页响应结构。
"""

import pytest
from rest_framework.test import APIClient

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


@pytest.fixture
def api():
    return APIClient()


def _slb_device(hostname: str = "_t_lb_slb") -> Device:
    return Device.objects.create(hostname=hostname, device_type="slb")


def _seed_ltm(device: Device):
    LtmVirtualServer.objects.create(
        device=device, name="/Common/vs_web", vs_address="10.0.0.100", vs_port="443", pool="pool_web"
    )
    LtmPool.objects.create(device=device, name="pool_web", mode="round-robin", monitors=["http"])
    LtmPoolMember.objects.create(
        device=device, pool_name="pool_web", name="/Common/node_a", address="10.1.1.1", port="80"
    )
    LtmPoolMember.objects.create(
        device=device, pool_name="pool_web", name="/Common/node_b", address="10.1.1.2", port="80"
    )


@pytest.mark.django_db
def test_ltm_chain_joins_pool_and_members(api):
    """一行 VS 带出池与全部成员（地址优先，name 原样保留供 hover）。"""
    _seed_ltm(_slb_device())

    results = api.get("/api/lb-chain/slb/").data["results"]

    assert len(results) == 1
    row = results[0]
    assert row["device_hostname"] == "_t_lb_slb"
    assert row["vs_address"] == "10.0.0.100"
    assert row["pool"] == {"name": "pool_web", "mode": "round-robin", "monitors": ["http"]}
    assert {(m["address"], m["port"]) for m in row["members"]} == {("10.1.1.1", "80"), ("10.1.1.2", "80")}
    # name 字段仍在，前端拿去做 hover 弹出
    assert {m["name"] for m in row["members"]} == {"/Common/node_a", "/Common/node_b"}


@pytest.mark.django_db
def test_ltm_chain_device_filter_and_member_address_search(api):
    """?device= 只看该设备；?search=成员地址 能反查到引用该池的 VS。"""
    dev_a, dev_b = _slb_device("_t_lb_a"), _slb_device("_t_lb_b")
    _seed_ltm(dev_a)
    LtmVirtualServer.objects.create(device=dev_b, name="vs_other", vs_address="10.9.9.9", vs_port="80")

    only_b = api.get("/api/lb-chain/slb/", {"device": dev_b.id}).data
    assert [r["name"] for r in only_b["results"]] == ["vs_other"]

    hit = api.get("/api/lb-chain/slb/", {"search": "10.1.1.2"}).data
    assert [r["name"] for r in hit["results"]] == ["/Common/vs_web"]
    miss = api.get("/api/lb-chain/slb/", {"search": "no-such-thing"}).data
    assert miss["count"] == 0


@pytest.mark.django_db
def test_ltm_chain_missing_pool_returns_null(api):
    """VS 没配池（或池记录缺失）时 pool 为 null、members 为空，不报错。"""
    LtmVirtualServer.objects.create(device=_slb_device(), name="vs_bare", vs_address="10.0.0.1", vs_port="80")

    row = api.get("/api/lb-chain/slb/").data["results"][0]

    assert row["pool"] is None
    assert row["members"] == []


def _gslb_device(hostname: str = "_t_lb_gslb") -> Device:
    return Device.objects.create(hostname=hostname, device_type="gslb")


def _seed_gtm(device: Device, members: list[dict]):
    GtmWideip.objects.create(device=device, name="www.example.com", rtype="A", lb_mode="global", pools=["pool_dns"])
    GtmPool.objects.create(device=device, name="pool_dns", members=members)


@pytest.mark.django_db
def test_gtm_chain_resolves_member_ip_via_vserver(api):
    """成员按 (device, server 名, vs 名) 折算出 IP/端口；server/vserver 名保留供 hover。"""
    device = _gslb_device()
    _seed_gtm(device, [{"server": "srv1", "vserver": "vs1", "status": "enabled"}])
    server = GtmServer.objects.create(device=device, name="srv1")
    GtmVServer.objects.create(device=device, server=server, name="vs1", ip_address="10.2.2.2", port="53")

    pool = api.get("/api/lb-chain/gslb/").data["results"][0]["pools"][0]

    assert pool["name"] == "pool_dns"
    member = pool["members"][0]
    assert member["found"] is True
    assert (member["address"], member["port"]) == ("10.2.2.2", "53")
    assert (member["server"], member["vserver"]) == ("srv1", "vs1")


@pytest.mark.django_db
def test_gtm_chain_unresolved_member_and_pool_search(api):
    """找不到 GtmVServer → found=False、address=None（前端回退显示名字）；
    ?search=池名 反查 wideip（pools 是 JSON 列表，走包含匹配）。"""
    device = _gslb_device()
    _seed_gtm(device, [{"server_name": "srv_x", "vs_name": "vs_x"}])  # 无对应 GtmVServer

    row = api.get("/api/lb-chain/gslb/").data["results"][0]
    member = row["pools"][0]["members"][0]
    assert member["found"] is False
    assert member["address"] is None

    hit = api.get("/api/lb-chain/gslb/", {"search": "pool_dns"}).data
    assert [r["name"] for r in hit["results"]] == ["www.example.com"]
    assert api.get("/api/lb-chain/gslb/", {"search": "www.example.com"}).data["count"] == 1
    assert api.get("/api/lb-chain/gslb/", {"search": "nothing-here"}).data["count"] == 0


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        ("10.0.0.1:443", ("10.0.0.1", "443")),  # IPv4 + 端口
        ("10.0.0.1#443", ("10.0.0.1", "443")),  # # 是项目展示层分隔符，天然无歧义
        ("2001:db8::1:80", ("2001:db8::1", "80")),  # IPv6 + 端口（最后一段是数字且地址不以冒号结尾）
        ("2001:db8::1", None),  # 纯 IPv6 不带端口：不能误拆成 (2001:db8:, 1)
        ("vs_web", None),  # 普通名字不拆
        ("10.0.0.1:", None),  # 端口为空
        ("10.0.0.1:abc", None),  # 端口非数字
        ("10.0.0.1:123456", None),  # 端口超过 5 位，按畸形词处理
    ],
)
def test_split_addr_port(term, expected):
    """地址端口拆分的边界：IPv6 不误拆、非数字/超长端口退化为整串模糊。"""
    from analysis.api.lb_chain import _split_addr_port

    assert _split_addr_port(term) == expected


@pytest.mark.django_db
def test_ltm_search_address_port_combo(api):
    """地址:端口 组合检索：VS 与池成员都要按 地址+端口 同时命中。

    覆盖 ?search= 的六种形态：vsname / vsaddress / vsaddress:port /
    poolname / poolmemberaddress / poolmemberaddress:port。
    """
    _seed_ltm(_slb_device())

    # vsaddress:port —— 跨字段组合，整串 icontains 做不到
    assert api.get("/api/lb-chain/slb/", {"search": "10.0.0.100:443"}).data["count"] == 1
    assert api.get("/api/lb-chain/slb/", {"search": "10.0.0.100#443"}).data["count"] == 1
    assert api.get("/api/lb-chain/slb/", {"search": "10.0.0.100:8443"}).data["count"] == 0
    # poolmemberaddress:port —— 成员按 地址+端口 命中后反查出引用该池的 VS
    hit = api.get("/api/lb-chain/slb/", {"search": "10.1.1.2:80"}).data
    assert [r["name"] for r in hit["results"]] == ["/Common/vs_web"]
    # 端口精确匹配：:80 不能命中 8080，:8 不能命中 80
    assert api.get("/api/lb-chain/slb/", {"search": "10.1.1.2:8080"}).data["count"] == 0
    assert api.get("/api/lb-chain/slb/", {"search": "10.1.1.2:8"}).data["count"] == 0
    # 单字段形态照旧：vsname / vsaddress / poolname / poolmemberaddress
    assert api.get("/api/lb-chain/slb/", {"search": "vs_web"}).data["count"] == 1
    assert api.get("/api/lb-chain/slb/", {"search": "10.0.0.100"}).data["count"] == 1
    assert api.get("/api/lb-chain/slb/", {"search": "pool_web"}).data["count"] == 1
    assert api.get("/api/lb-chain/slb/", {"search": "10.1.1.1"}).data["count"] == 1


@pytest.mark.django_db
def test_ltm_search_ipv6_not_mis_split(api):
    """IPv6 自带冒号：不带端口的整串搜索不能被误拆成 地址+端口。"""
    dev = _slb_device("_t_lb_v6")
    LtmVirtualServer.objects.create(device=dev, name="vs_v6", vs_address="2001:db8::1", vs_port="443")

    # 整串模糊命中（若被误拆成 port=1 就会漏）
    assert api.get("/api/lb-chain/slb/", {"search": "2001:db8::1"}).data["count"] == 1
    # 拆出端口的组合形态
    assert api.get("/api/lb-chain/slb/", {"search": "2001:db8::1:443"}).data["count"] == 1
    assert api.get("/api/lb-chain/slb/", {"search": "2001:db8::1:80"}).data["count"] == 0


@pytest.mark.django_db
def test_chain_endpoints_paginated(api):
    """两个端点都返回 {count, next, previous, results} 的标准分页结构。"""
    for i in range(3):
        LtmVirtualServer.objects.create(
            device=_slb_device(f"_t_lb_pg{i}"), name=f"vs_{i}", vs_address=f"10.0.{i}.1", vs_port="80"
        )
    GtmWideip.objects.create(device=_gslb_device("_t_lb_pg_g"), name="a.example.com")

    for url in ("/api/lb-chain/slb/", "/api/lb-chain/gslb/"):
        data = api.get(url).data
        assert set(data) == {"count", "next", "previous", "results"}
        assert isinstance(data["results"], list)
