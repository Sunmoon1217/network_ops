"""GSLB 集群分析接口（``/api/analysis/gslb-clusters/*``）测试。

覆盖四件事：① 集群划分（cluster 组 / 单机集群 / 一机多组取第一个）；
② 逐层合并（WideIP→池→成员并集去重、device 逗号拼接、标量以主机名第一台为准）；
③ 不一致标记（同名配置不同 → ``inconsistent`` + ``conflict_fields``）；
④ 过滤 / 搜索 / 分页 / facets / 导出。
"""

from io import BytesIO

import pytest
from openpyxl import load_workbook
from rest_framework.test import APIClient

from assets.models import Device, DeviceGroup, DeviceGroupMember, GtmPool, GtmServer, GtmVServer, GtmWideip

BASE = "/api/analysis/gslb-clusters/"


@pytest.fixture
def api():
    return APIClient()


def _device(hostname: str, device_type: str = "gslb") -> Device:
    return Device.objects.create(hostname=hostname, device_type=device_type)


def _cluster_group(name: str, devices: list[Device]) -> DeviceGroup:
    group = DeviceGroup.objects.create(name=name, group_type="cluster")
    for device in devices:
        DeviceGroupMember.objects.create(group=group, device=device)
    return group


def _wideip(device, name="www.example.com", rtype="A", lb_mode="global", pools=None) -> GtmWideip:
    return GtmWideip.objects.create(
        device=device, name=name, rtype=rtype, lb_mode=lb_mode, pools=pools if pools is not None else ["pool_dns"]
    )


def _pool(device, name="pool_dns", members=None, **kwargs) -> GtmPool:
    return GtmPool.objects.create(device=device, name=name, members=members or [], **kwargs)


def _vserver(device, server_name, vs_name, address, port="") -> GtmVServer:
    server, _ = GtmServer.objects.get_or_create(device=device, name=server_name, defaults={"datacenter": "DC1"})
    return GtmVServer.objects.create(device=device, server=server, name=vs_name, ip_address=address, port=port)


def _read_xlsx(resp):
    return load_workbook(BytesIO(resp.content)).active


@pytest.mark.django_db
def test_cluster_groups_devices_and_standalone_becomes_singleton(api):
    """cluster 组的成员合并成一个集群（device 逗号拼接）；未入组的 GSLB 设备是单机集群。"""
    a, b, solo = _device("gtm-a"), _device("gtm-b"), _device("gtm-solo")
    group = _cluster_group("cs-gtm", [a, b])
    for device in (a, b, solo):
        _wideip(device)
        _pool(device)

    rows = api.get(BASE).data["results"]
    by_cluster = {row["cluster_name"]: row for row in rows}

    merged = by_cluster["cs-gtm"]
    assert merged["cluster"] == f"group-{group.id}"
    assert merged["device"] == "gtm-a,gtm-b"
    assert [item["hostname"] for item in merged["cluster_devices"]] == ["gtm-a", "gtm-b"]

    single = by_cluster["gtm-solo"]
    assert single["cluster"] == f"device-{solo.id}"
    assert single["device"] == "gtm-solo"
    assert single["cluster_devices"] == [{"id": solo.id, "hostname": "gtm-solo"}]


@pytest.mark.django_db
def test_layer_by_layer_union_and_per_entry_device(api):
    """逐层并集去重：池/成员按身份合并，每个条目的 device 只拼「出现它的设备」。"""
    a, b = _device("gtm-a"), _device("gtm-b")
    _cluster_group("cs-gtm", [a, b])
    shared_a = [{"server": "s1", "vserver": "vs1", "order": 1}]
    shared_b = [{"server": "s1", "vserver": "vs1", "order": 1}, {"server": "s2", "vserver": "vs2", "order": 2}]
    _wideip(a, pools=["pool_shared", "pool_a_only"])
    _wideip(b, pools=["pool_shared", "pool_b_only"])
    _pool(a, "pool_shared", shared_a)
    _pool(b, "pool_shared", shared_b)
    _pool(a, "pool_a_only")
    _pool(b, "pool_b_only")
    _vserver(a, "s1", "vs1", "10.1.1.1", "80")
    _vserver(b, "s1", "vs1", "10.1.1.1", "80")
    _vserver(b, "s2", "vs2", "10.1.1.2", "80")

    row = api.get(BASE).data["results"][0]
    assert row["device"] == "gtm-a,gtm-b"

    pools = {pool["name"]: pool for pool in row["pools"]}
    # 池名并集按首次出现顺序：a 的池在前，b 独有池在后
    assert [pool["name"] for pool in row["pools"]] == ["pool_shared", "pool_a_only", "pool_b_only"]
    assert pools["pool_shared"]["device"] == "gtm-a,gtm-b"
    assert pools["pool_a_only"]["device"] == "gtm-a"
    assert pools["pool_b_only"]["device"] == "gtm-b"

    shared_members = {member["vserver"]: member for member in pools["pool_shared"]["members"]}
    assert shared_members["vs1"]["device"] == "gtm-a,gtm-b"
    assert shared_members["vs2"]["device"] == "gtm-b"
    assert shared_members["vs2"]["found"] is True
    assert shared_members["vs2"]["address"] == "10.1.1.2"

    # 池集合不同 + 池内成员集合不同 → 两层都标记不一致
    assert row["inconsistent"] is True
    assert "pools" in row["conflict_fields"]
    assert "members" in pools["pool_shared"]["conflict_fields"]


@pytest.mark.django_db
def test_scalar_conflict_takes_first_hostname_and_flags(api):
    """同名 WideIP 标量不同：取主机名排序第一台，并逐字段标出冲突。"""
    a, b = _device("gtm-a"), _device("gtm-b")
    _cluster_group("cs-gtm", [a, b])
    # 故意让「第二台」构造在前，验证最终取的是主机名第一台而不是插入顺序
    _wideip(b, lb_mode="topology")
    _wideip(a, lb_mode="global")
    _pool(b, lb_mode="topology")
    _pool(a, lb_mode="round-robin", ttl=60)

    row = api.get(BASE).data["results"][0]
    assert row["lb_mode"] == "global"
    assert row["inconsistent"] is True
    assert row["conflict_fields"] == ["lb_mode"]

    pool = row["pools"][0]
    assert pool["lb_mode"] == "round-robin"
    assert pool["ttl"] == 60
    assert pool["inconsistent"] is True
    assert set(pool["conflict_fields"]) == {"lb_mode", "ttl"}


@pytest.mark.django_db
def test_member_address_conflict_flagged(api):
    """同一成员在不同设备上解析出不同地址 → 成员标不一致，取第一台。"""
    a, b = _device("gtm-a"), _device("gtm-b")
    _cluster_group("cs-gtm", [a, b])
    member = [{"server": "s1", "vserver": "vs1"}]
    for device in (a, b):
        _wideip(device)
        _pool(device, members=member)
    _vserver(a, "s1", "vs1", "10.1.1.1", "80")
    _vserver(b, "s1", "vs1", "10.9.9.9", "80")

    row = api.get(BASE).data["results"][0]
    merged = row["pools"][0]["members"][0]
    assert merged["device"] == "gtm-a,gtm-b"
    assert merged["address"] == "10.1.1.1"
    assert merged["inconsistent"] is True
    assert "address" in merged["conflict_fields"]


@pytest.mark.django_db
def test_device_filter_selects_whole_cluster(api):
    """?device= 命中集群内任一设备 → 返回整条集群合并行（不是该设备自己的行）。"""
    a, b, other = _device("gtm-a"), _device("gtm-b"), _device("gtm-other")
    _cluster_group("cs-gtm", [a, b])
    for device in (a, b, other):
        _wideip(device)
        _pool(device)

    for device in (a, b):
        results = api.get(BASE, {"device": device.id}).data["results"]
        assert [row["device"] for row in results] == ["gtm-a,gtm-b"]

    singleton = api.get(BASE, {"device": other.id}).data["results"]
    assert [row["device"] for row in singleton] == ["gtm-other"]
    # 非 GSLB 设备 id 不产生任何集群
    slb = _device("some-slb", device_type="slb")
    assert api.get(BASE, {"device": slb.id}).data["count"] == 0
    # 设备 id 非法 → 空结果（不静默退化成全量）
    assert api.get(BASE, {"device": "abc"}).data["count"] == 0


@pytest.mark.django_db
def test_device_in_multiple_clusters_goes_to_first_group(api):
    """一台设备落在多个集群组时只进（组名, id）排序第一个，避免重复出现在两个集群。"""
    device = _device("gtm-a")
    _cluster_group("zeta", [device])
    _cluster_group("alpha", [device])
    _wideip(device)
    _pool(device)

    rows = api.get(BASE).data["results"]
    assert [row["cluster_name"] for row in rows] == ["alpha"]
    assert rows[0]["device"] == "gtm-a"


@pytest.mark.django_db
def test_rtype_monitor_and_search_filters(api):
    """rtype / monitor / search（域名、池名、服务器、地址#端口）过滤。"""
    device = _device("gtm-a")
    _wideip(device, name="www.example.com", rtype="A", pools=["pool_web"])
    _wideip(device, name="api.example.com", rtype="AAAA", pools=["pool_api"])
    _pool(device, "pool_web", [{"server": "srv1", "vserver": "vs1"}], monitor=["http"])
    _pool(device, "pool_api", [{"server": "srv2", "vserver": "vs2"}], monitor=["icmp"])
    _vserver(device, "srv1", "vs1", "10.1.1.1", "80")
    _vserver(device, "srv2", "vs2", "10.1.1.2", "443")

    def names(params):
        return [row["name"] for row in api.get(BASE, params).data["results"]]

    assert names({"rtype": "aaaa"}) == ["api.example.com"]
    assert names({"monitor": "http"}) == ["www.example.com"]
    assert names({"search": "api"}) == ["api.example.com"]
    assert names({"search": "pool_web"}) == ["www.example.com"]
    assert names({"search": "srv2"}) == ["api.example.com"]
    assert names({"search": "10.1.1.1#80"}) == ["www.example.com"]
    assert names({"search": "10.1.1.1:80"}) == ["www.example.com"]
    assert names({"search": "nothing"}) == []
    # 集群维度也参与搜索：按集群里另一台设备的主机名能搜到合并行
    assert names({"search": "gtm-a"}) == ["api.example.com", "www.example.com"]


@pytest.mark.django_db
def test_ordering_and_pagination(api):
    """默认按 集群名 + 域名 排；?ordering= 可切；响应是标准分页结构。"""
    device = _device("gtm-a")
    for name in ("b.example.com", "a.example.com", "c.example.com"):
        _wideip(device, name=name)
        _pool(device, name=f"pool_{name}")

    payload = api.get(BASE).data
    assert set(payload) == {"count", "next", "previous", "results"}
    assert [row["name"] for row in payload["results"]] == ["a.example.com", "b.example.com", "c.example.com"]

    desc = api.get(BASE, {"ordering": "-name"}).data["results"]
    assert [row["name"] for row in desc] == ["c.example.com", "b.example.com", "a.example.com"]

    first_page = api.get(BASE, {"page_size": 2}).data
    assert first_page["count"] == 3
    assert len(first_page["results"]) == 2
    assert first_page["next"]


@pytest.mark.django_db
def test_cluster_filter_accepts_key_and_group_name(api):
    """?cluster= 既认集群键，也认组名（前端下拉用键，人工调接口更顺手写组名）。"""
    a, b, solo = _device("gtm-a"), _device("gtm-b"), _device("gtm-solo")
    group = _cluster_group("cs-gtm", [a, b])
    for device in (a, b, solo):
        _wideip(device)
        _pool(device)

    by_key = api.get(BASE, {"cluster": f"group-{group.id}"}).data
    assert [row["device"] for row in by_key["results"]] == ["gtm-a,gtm-b"]

    by_name = api.get(BASE, {"cluster": "cs-gtm"}).data
    assert [row["device"] for row in by_name["results"]] == ["gtm-a,gtm-b"]

    single = api.get(BASE, {"cluster": "gtm-solo"}).data
    assert [row["device"] for row in single["results"]] == ["gtm-solo"]
    assert api.get(BASE, {"cluster": "nope"}).data["count"] == 0


@pytest.mark.django_db
def test_facets_match_legacy_gtm_endpoint(api):
    """集群接口的 facets：rtypes/monitors 与旧接口同口径，clusters 是独有的过滤器选项。"""
    device = _device("gtm-a")
    _wideip(device, name="www.example.com", rtype="A", pools=["pool_web"])
    _pool(device, "pool_web", [{"server": "srv1", "vserver": "vs1"}], monitor=["http"])
    _vserver(device, "srv1", "vs1", "10.1.1.1", "80")

    cluster_facets = api.get(f"{BASE}facets/").data
    legacy_facets = api.get("/api/lb-chain/gslb/facets/").data
    assert {key: cluster_facets[key] for key in ("rtypes", "monitors")} == legacy_facets
    assert cluster_facets["rtypes"] == ["A"]
    assert "http" in cluster_facets["monitors"]
    # 单机集群：group_id 为 null，name 即设备名
    assert cluster_facets["clusters"] == [
        {"key": f"device-{device.id}", "name": "gtm-a", "group_id": None, "devices": ["gtm-a"]}
    ]


@pytest.mark.django_db
def test_export_flat_rows_includes_device_join_and_inconsistency(api):
    """导出：设备列是逗号拼接串，末列标出不一致；列宽与表头一一对应。"""
    from analysis.api.gslb_clusters import CLUSTER_EXPORT_COLUMN_WIDTHS, CLUSTER_EXPORT_HEADERS

    a, b = _device("gtm-a"), _device("gtm-b")
    _cluster_group("cs-gtm", [a, b])
    for device in (a, b):
        _wideip(device)
        _pool(device, members=[{"server": "s1", "vserver": "vs1", "order": 1}])
    _vserver(a, "s1", "vs1", "10.1.1.1", "80")
    _vserver(b, "s1", "vs1", "10.1.1.1", "80")
    # 同名域名两边都在、但引用的池不同 → 命中「配置不一致」
    _wideip(a, name="drift.example.com", pools=["pool_drift"])
    _wideip(b, name="drift.example.com", pools=["pool_other"])
    _pool(a, "pool_drift")
    _pool(b, "pool_other")

    resp = api.get(f"{BASE}export/")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("application/vnd.openxmlformats")

    assert len(CLUSTER_EXPORT_COLUMN_WIDTHS) == len(CLUSTER_EXPORT_HEADERS)
    sheet = _read_xlsx(resp)
    assert [cell.value for cell in sheet[1]] == CLUSTER_EXPORT_HEADERS
    rows = [[cell.value for cell in row] for row in sheet.iter_rows(min_row=2)]

    merged = [row for row in rows if row[1] == "www.example.com"][0]
    assert merged[0] == "gtm-a,gtm-b"
    assert merged[11] == "10.1.1.1#80"
    assert merged[17] in ("", None)  # 全等 → 不标不一致

    drift = [row for row in rows if row[1] == "drift.example.com"]
    assert {row[6] for row in drift} == {"pool_drift", "pool_other"}  # 并集各占一行
    assert {row[17] for row in drift} == {"是"}  # 池集合不一致 → 都标「是」
