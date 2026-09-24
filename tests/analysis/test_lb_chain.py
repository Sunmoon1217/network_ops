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
        device=device,
        name="/Common/vs_web",
        vs_address="10.0.0.100",
        vs_port="443",
        pool="pool_web",
        profiles=["/Common/http", "/Common/tcp"],
        rules=["/Common/irule_redirect"],
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
    # 一级 VS 行单独展示的字段：profile / iRule 名字列表随行返回
    assert row["profiles"] == ["/Common/http", "/Common/tcp"]
    assert row["rules"] == ["/Common/irule_redirect"]
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
    """成员按 (device, server 名, vs 名) 折算出 IP/端口；server/vserver 名保留供 hover，
    并携带二级/三级增列字段：池级 算法与 fallback、成员级 order/ratio/monitor/datacenter。"""
    device = _gslb_device()
    _seed_gtm(
        device,
        [{"server": "srv1", "vserver": "vs1", "status": "enabled", "order": 2, "ratio": 10, "monitor": "icmp"}],
    )
    server = GtmServer.objects.create(device=device, name="srv1", datacenter="DC1")
    GtmVServer.objects.create(device=device, server=server, name="vs1", ip_address="10.2.2.2", port="53")

    pool = api.get("/api/lb-chain/gslb/").data["results"][0]["pools"][0]

    assert pool["name"] == "pool_dns"
    # 二级：负载算法与 fallback 是 GtmPool 的模型字段（默认值）
    assert pool["lb_mode"] == "round-robin"
    assert pool["alternate_mode"] == "round-robin"
    assert pool["fallback_mode"] == "return-to-dns"
    member = pool["members"][0]
    assert member["found"] is True
    assert (member["address"], member["port"]) == ("10.2.2.2", "53")
    assert (member["server"], member["vserver"]) == ("srv1", "vs1")
    # 三级：成员调度权重 + 成员级健康检查 + 所属 server 的数据中心
    assert (member["order"], member["ratio"], member["monitor"]) == (2, 10, "icmp")
    assert member["datacenter"] == "DC1"


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


# ---------------------------------------------------------------------------
# GTM 搜索六形态 / 过滤 / facets
# ---------------------------------------------------------------------------


def _seed_gtm_search(device: Device):
    """搜索与过滤测试的共用底座：www(A) → pool_dns → srvA/vsA；api(AAAA) → pool_b → srvB/vsB。"""
    _seed_gtm(device, [{"server": "srvA", "vserver": "vsA"}])
    GtmWideip.objects.create(
        device=device, name="api.example.com", rtype="AAAA", lb_mode="round-robin", pools=["pool_b"]
    )
    GtmPool.objects.create(
        device=device, name="pool_b", members=[{"server": "srvB", "vserver": "vsB"}], monitor=["gtm_tcp"]
    )
    GtmPool.objects.filter(name="pool_dns").update(monitor=["gtm_https", "icmp"])
    srv_a = GtmServer.objects.create(device=device, name="srvA", monitor="icmp")
    GtmVServer.objects.create(device=device, server=srv_a, name="vsA", ip_address="10.9.9.1", port="53", monitor="dns")
    srv_b = GtmServer.objects.create(device=device, name="srvB")
    GtmVServer.objects.create(device=device, server=srv_b, name="vsB", ip_address="10.9.9.2", port="443")


@pytest.mark.django_db
def test_gtm_search_forms(api):
    """六种搜索形态：wideipname / poolname / servername / vservername /
    vserveraddress / vserveraddress:port，外加健康检查名搜索。"""
    _seed_gtm_search(_gslb_device())

    def count(term: str) -> int:
        return api.get("/api/lb-chain/gslb/", {"search": term}).data["count"]

    assert count("www.example.com") == 1  # wideipname
    assert count("pool_dns") == 1  # poolname（沿链反查）
    assert count("srvA") == 1  # servername（池成员引用反查）
    assert count("vsA") == 1  # vservername
    assert count("10.9.9.1") == 1  # vserveraddress
    assert count("10.9.9.1:53") == 1  # 组合命中
    assert count("10.9.9.1:443") == 0  # 端口不匹配（地址与端口都不能混）
    assert count("icmp") == 1  # 池 monitor + 服务器 monitor 都命中 www（同一条 wideip）
    assert count("gtm_tcp") == 1  # 池 monitor → api.example.com
    assert count("dns") == 1  # 虚拟服务器 monitor → 池成员反查 → www


@pytest.mark.django_db
def test_gtm_rtype_and_monitor_filters(api):
    """?rtype= 记录类型精确过滤；?monitor= 健康检查类型过滤（三处 monitor 命中其一）。"""
    device = _gslb_device()
    _seed_gtm_search(device)

    aaa = api.get("/api/lb-chain/gslb/", {"rtype": "AAAA"}).data
    assert [r["name"] for r in aaa["results"]] == ["api.example.com"]
    a = api.get("/api/lb-chain/gslb/", {"rtype": "A"}).data
    assert [r["name"] for r in a["results"]] == ["www.example.com"]

    hit = api.get("/api/lb-chain/gslb/", {"monitor": "icmp"}).data
    assert [r["name"] for r in hit["results"]] == ["www.example.com"]
    assert api.get("/api/lb-chain/gslb/", {"monitor": "no-such-monitor"}).data["count"] == 0
    # 过滤与搜索可叠加
    both = api.get("/api/lb-chain/gslb/", {"rtype": "A", "monitor": "gtm_https"}).data
    assert [r["name"] for r in both["results"]] == ["www.example.com"]
    assert api.get("/api/lb-chain/gslb/", {"rtype": "AAAA", "monitor": "gtm_https"}).data["count"] == 0


@pytest.mark.django_db
def test_gtm_facets(api):
    """facets 返回过滤下拉选项：rtype 去重 + 三处 monitor 合集（池 JSON 列表展开）。"""
    _seed_gtm_search(_gslb_device())

    data = api.get("/api/lb-chain/gslb/facets/").data
    assert data["rtypes"] == ["A", "AAAA"]
    assert data["monitors"] == ["dns", "gtm_https", "gtm_tcp", "icmp"]
