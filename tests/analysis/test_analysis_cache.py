"""互联网资产分析缓存行为测试。

分析要遍历 GTM/LTM 多张表并在内存里做关联，成本不低；所以只在手动触发
「立即分析」时计算并写入 InternetAnalysis 缓存，查询与导出都只读缓存。
这里固化三条规则：GET 不触发计算、POST 才写缓存、没有缓存时 404。
"""

import pytest
from django.test import Client

from analysis.models import InternetAnalysis
from assets.models import Device, GtmPool, GtmServer, GtmVServer, GtmWideip, ServerOwner

LIST_URL = "/api/internet-analysis/"
ANALYZE_URL = "/api/internet-analysis/analyze/"
EXPORT_URL = "/api/internet-analysis/export/"


def _build_chain(hostname: str = "ia-cache") -> Device:
    """一条最小的 GTM 链路：WideIP → Pool → 成员 → GTM 虚拟服务器"""
    gslb = Device.objects.create(hostname=hostname, device_type="gslb")
    GtmWideip.objects.create(device=gslb, name="www.example.com", rtype="A", pools=["pool_web"])
    GtmPool.objects.create(device=gslb, name="pool_web", members=[{"server_name": "s1", "vs_name": "vs1"}])
    server = GtmServer.objects.create(device=gslb, name="s1")
    GtmVServer.objects.create(device=gslb, server=server, name="vs1", ip_address="10.1.1.1", port="80")
    return gslb


@pytest.mark.django_db
def test_list_without_cache_returns_404():
    """没分析过时查询应明确告知，而不是顺手算一遍"""
    gslb = _build_chain("ia-cache-none")

    res = Client().get(LIST_URL, {"device": gslb.pk})

    assert res.status_code == 404
    assert res.json()["error"] == "该设备尚未分析"
    assert InternetAnalysis.objects.filter(device=gslb).count() == 0


@pytest.mark.django_db
def test_analyze_writes_cache():
    """POST analyze 才真正计算并落库"""
    gslb = _build_chain("ia-cache-run")

    res = Client().post(f"{ANALYZE_URL}?device={gslb.pk}")

    assert res.status_code == 200
    body = res.json()
    assert body["wideips"][0]["name"] == "www.example.com"
    assert body["analyzed_at"] is not None
    assert "duration_ms" in body

    cached = InternetAnalysis.objects.get(device=gslb)
    assert cached.result["wideips"][0]["name"] == "www.example.com"


@pytest.mark.django_db
def test_list_returns_cache_without_recomputing():
    """关键：查询只读缓存——分析之后再改数据，查询结果不应变化"""
    gslb = _build_chain("ia-cache-read")
    Client().post(f"{ANALYZE_URL}?device={gslb.pk}")

    # 分析完成后再加一个 WideIP，命中缓存的话查询结果里不该出现它
    GtmWideip.objects.create(device=gslb, name="later.example.com", rtype="A", pools=[])

    res = Client().get(LIST_URL, {"device": gslb.pk})

    assert res.status_code == 200
    names = [wideip["name"] for wideip in res.json()["wideips"]]
    assert names == ["www.example.com"]
    assert "later.example.com" not in names


@pytest.mark.django_db
def test_analyze_overwrites_previous_result():
    """重复分析覆盖同一份缓存，不会堆积多条"""
    gslb = _build_chain("ia-cache-idem")

    Client().post(f"{ANALYZE_URL}?device={gslb.pk}")
    Client().post(f"{ANALYZE_URL}?device={gslb.pk}")

    assert InternetAnalysis.objects.filter(device=gslb).count() == 1


@pytest.mark.django_db
def test_export_without_cache_returns_404():
    """导出同样只读缓存，没分析过就提示先分析"""
    gslb = _build_chain("ia-cache-exp")

    res = Client().get(EXPORT_URL, {"device": gslb.pk})

    assert res.status_code == 404
    assert "尚未分析" in res.json()["error"]


@pytest.mark.django_db
def test_analyze_requires_device_param():
    assert Client().post(ANALYZE_URL).status_code == 400


@pytest.mark.django_db
def test_analyze_unknown_device_returns_404():
    assert Client().post(f"{ANALYZE_URL}?device=999999").status_code == 404


# ---------- 负责人映射（前端表格自己扁平化，靠这份映射填「负责人」列） ----------


@pytest.mark.django_db
def test_list_returns_owner_map_keyed_by_final_ip():
    """owners 的键是链路最后的 IP 的原始写法，值是负责人"""
    gslb = _build_chain("ia-cache-owner")
    ServerOwner.objects.create(ip="10.1.1.1", owner="张三")
    Client().post(f"{ANALYZE_URL}?device={gslb.pk}")

    payload = Client().get(LIST_URL, {"device": gslb.pk}).json()

    # 这条链路没有对应的 LTM 虚拟服务器，最后的 IP 回退到 GTM 虚拟服务器地址
    assert payload["owners"] == {"10.1.1.1": "张三"}
    assert payload["analyzed_at"]


@pytest.mark.django_db
def test_owner_map_reflects_edits_without_reanalysis():
    """负责人是人工维护的，改了不必重跑分析就能看到"""
    gslb = _build_chain("ia-cache-owner-edit")
    owner = ServerOwner.objects.create(ip="10.1.1.1", owner="张三")
    Client().post(f"{ANALYZE_URL}?device={gslb.pk}")

    owner.owner = "李四"
    owner.save(update_fields=["owner"])

    payload = Client().get(LIST_URL, {"device": gslb.pk}).json()

    assert payload["owners"] == {"10.1.1.1": "李四"}


@pytest.mark.django_db
def test_owner_map_skips_disabled_and_ownerless_records():
    gslb = _build_chain("ia-cache-owner-skip")
    ServerOwner.objects.create(ip="10.1.1.1", owner="已停用", status="disabled")
    Client().post(f"{ANALYZE_URL}?device={gslb.pk}")

    payload = Client().get(LIST_URL, {"device": gslb.pk}).json()

    assert payload["owners"] == {}
