"""SLB / GSLB 列表接口的搜索与设备过滤测试。

前端「负载均衡 / 域名解析」页面加了搜索框与设备下拉，接口侧的契约：

- ``search`` 要覆盖各页面实际展示的核心字段（名称、地址、池、模式、记录类型、设备主机名），
  只搜 name 的话搜索框对「按地址/按设备找」是摆设；
- ``device`` 过滤保持不变；
- 设备下拉按 ``device_type`` 收窄（负载均衡页只列 slb、域名解析页只列 gslb），
  依赖 /api/assets/devices/ 的 device_type 查询参数。
"""

import pytest
from rest_framework.test import APIClient

from assets.models import Device, GtmPool, GtmWideip, LtmPool, LtmVirtualServer


@pytest.fixture
def client():
    return APIClient()


def _device(hostname: str, device_type: str) -> Device:
    return Device.objects.create(hostname=hostname, device_type=device_type)


@pytest.mark.django_db
def test_virtual_server_search_covers_address_pool_and_hostname(client):
    """搜虚拟地址 / 池名 / 设备主机名都要能命中，不只是名称"""
    slb_a = _device("slb-edge-01", "slb")
    slb_b = _device("slb-edge-02", "slb")
    LtmVirtualServer.objects.create(device=slb_a, name="vs_web", vs_address="192.0.2.10", pool="pool_web")
    LtmVirtualServer.objects.create(device=slb_b, name="vs_api", vs_address="198.51.100.20", pool="pool_api")

    assert client.get("/api/assets/ltm-virtual-servers/", {"search": "192.0.2"}).json()["count"] == 1
    assert client.get("/api/assets/ltm-virtual-servers/", {"search": "pool_api"}).json()["count"] == 1
    assert client.get("/api/assets/ltm-virtual-servers/", {"search": "slb-edge-02"}).json()["count"] == 1


@pytest.mark.django_db
def test_ltm_pool_search_covers_mode(client):
    slb = _device("slb-pool-01", "slb")
    LtmPool.objects.create(device=slb, name="pool_web", mode="round-robin")
    LtmPool.objects.create(device=slb, name="pool_db", mode="least-connections")

    assert client.get("/api/assets/ltm-pools/", {"search": "least-conn"}).json()["count"] == 1


@pytest.mark.django_db
def test_wideip_search_covers_rtype_and_hostname(client):
    gslb = _device("gslb-dns-01", "gslb")
    GtmWideip.objects.create(device=gslb, name="www.example.com", rtype="A", lb_mode="global-availability")
    GtmWideip.objects.create(device=gslb, name="mail.example.com", rtype="AAAA", lb_mode="round-robin")

    assert client.get("/api/assets/gtm-wideips/", {"search": "AAAA"}).json()["count"] == 1
    assert client.get("/api/assets/gtm-wideips/", {"search": "gslb-dns"}).json()["count"] == 2
    assert client.get("/api/assets/gtm-wideips/", {"search": "www.example"}).json()["count"] == 1


@pytest.mark.django_db
def test_gtm_pool_search_covers_fallback_ip(client):
    gslb = _device("gslb-dns-02", "gslb")
    GtmPool.objects.create(device=gslb, name="pool_us", fallback_ip="203.0.113.1")
    GtmPool.objects.create(device=gslb, name="pool_eu", fallback_ip="203.0.113.2")

    assert client.get("/api/assets/gtm-pools/", {"search": "203.0.113.1"}).json()["count"] == 1


@pytest.mark.django_db
def test_ltm_and_gtm_lists_can_filter_by_device(client):
    """device 过滤是设备下拉的落点：两台设备各有数据时只能查到自己那台"""
    slb_a = _device("slb-edge-03", "slb")
    slb_b = _device("slb-edge-04", "slb")
    LtmVirtualServer.objects.create(device=slb_a, name="vs_a", vs_address="192.0.2.1")
    LtmVirtualServer.objects.create(device=slb_b, name="vs_b", vs_address="192.0.2.2")

    payload = client.get("/api/assets/ltm-virtual-servers/", {"device": slb_a.pk}).json()

    assert payload["count"] == 1
    assert payload["results"][0]["name"] == "vs_a"


@pytest.mark.django_db
def test_device_list_can_filter_by_device_type(client):
    """设备下拉按类型收窄：负载均衡页只列 slb、域名解析页只列 gslb"""
    _device("slb-edge-05", "slb")
    _device("gslb-dns-03", "gslb")
    _device("fw-core-01", "firewall")

    slb_rows = client.get("/api/assets/devices/", {"device_type": "slb"}).json()["results"]
    gslb_rows = client.get("/api/assets/devices/", {"device_type": "gslb"}).json()["results"]
    slb_names = {row["hostname"] for row in slb_rows}
    gslb_names = {row["hostname"] for row in gslb_rows}

    assert slb_names == {"slb-edge-05"}
    assert gslb_names == {"gslb-dns-03"}
