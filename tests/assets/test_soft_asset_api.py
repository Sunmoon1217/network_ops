"""软资产只读 API（T4）的契约测试：列表 / 搜索 / 过滤 / 只读。"""

import pytest

from assets.models import Device, DomainAsset, GtmPool, GtmServer, GtmVServer, GtmWideip, LoadBalancerService, LtmPoolMember, LtmVirtualServer
from assets.services.soft_asset_sync import sync_soft_assets

DOMAIN_URL = "/api/assets/domain-assets/"
SERVICE_URL = "/api/assets/load-balancer-services/"


def _gtm(hostname: str, fqdn: str, lb_mode: str = "round-robin") -> None:
    device = Device.objects.create(hostname=hostname, device_type="gslb")
    server = GtmServer.objects.create(device=device, name="srv1")
    GtmVServer.objects.create(server=server, device=device, name="vs1", ip_address="10.0.0.1", port="80")
    GtmPool.objects.create(device=device, name="pool_web", ttl=30, fallback_ip="1.1.1.1", members=[{"server": "srv1", "vserver": "vs1"}])
    GtmWideip.objects.create(device=device, name=fqdn, rtype="A", lb_mode=lb_mode, pools=["pool_web"])


def _ltm(hostname: str, address: str, port: str) -> None:
    device = Device.objects.create(hostname=hostname, device_type="slb")
    LtmPoolMember.objects.create(device=device, pool_name="pool_web", name="node1", address="192.168.1.1", port="8080")
    LtmVirtualServer.objects.create(device=device, name="vs_web", vs_address=address, vs_port=port, protocol="tcp", status="enabled", pool="pool_web")


@pytest.mark.django_db
def test_domain_asset_list(api_client):
    _gtm("gtm-a", "a.example.com")
    sync_soft_assets("domain")

    res = api_client.get(DOMAIN_URL)

    assert res.status_code == 200
    assert res.data["count"] == 1
    row = res.data["results"][0]
    assert row["fqdn"] == "a.example.com"
    assert row["ci_id"].startswith("CI-")
    assert row["devices"] == ["gtm-a"]
    assert row["vips"] == ["10.0.0.1#80"]
    assert row["inconsistent"] is False


@pytest.mark.django_db
def test_domain_asset_search_and_filters(api_client):
    _gtm("gtm-a", "a.example.com")
    _gtm("gtm-b", "a.example.com", lb_mode="topology")  # 同 FQDN 取值不同 → 冲突
    _gtm("gtm-c", "b.example.com")
    sync_soft_assets("domain")

    assert api_client.get(DOMAIN_URL, {"search": "a.example"}).data["count"] == 1
    assert api_client.get(DOMAIN_URL, {"search": "nope"}).data["count"] == 0
    assert api_client.get(DOMAIN_URL, {"inconsistent": "true"}).data["count"] == 1
    assert api_client.get(DOMAIN_URL, {"inconsistent": "false"}).data["count"] == 1
    assert api_client.get(DOMAIN_URL, {"device": "gtm-a"}).data["count"] == 1
    assert api_client.get(DOMAIN_URL, {"vip": "10.0.0.1#80"}).data["count"] == 2
    assert api_client.get(DOMAIN_URL, {"vip": "10.9.9.9#443"}).data["count"] == 0


@pytest.mark.django_db
def test_load_balancer_service_list_and_filters(api_client):
    _ltm("slb-a", "10.1.1.10", "443")
    _ltm("slb-b", "10.1.1.10", "80")
    sync_soft_assets("lb")

    res = api_client.get(SERVICE_URL)
    assert res.status_code == 200
    assert res.data["count"] == 2

    assert api_client.get(SERVICE_URL, {"port": "443"}).data["count"] == 1
    assert api_client.get(SERVICE_URL, {"status": "enabled"}).data["count"] == 2
    assert api_client.get(SERVICE_URL, {"device": "slb-a"}).data["count"] == 1
    assert api_client.get(SERVICE_URL, {"search": "10.1.1.10"}).data["count"] == 2


@pytest.mark.django_db
def test_soft_asset_endpoints_are_read_only(operator_client):
    """归并字段只能由 sync_soft_assets 写：操作员也不能通过 API 改"""
    _gtm("gtm-a", "a.example.com")
    _ltm("slb-a", "10.1.1.10", "443")
    sync_soft_assets()

    assert operator_client.post(DOMAIN_URL, {"fqdn": "x.example.com"}, format="json").status_code == 405
    domain_id = DomainAsset.objects.get().pk
    assert operator_client.patch(f"{DOMAIN_URL}{domain_id}/", {"ttl": 1}, format="json").status_code == 405

    assert operator_client.post(SERVICE_URL, {"asset_key": "1.1.1.1#80"}, format="json").status_code == 405
    service_id = LoadBalancerService.objects.get().pk
    assert operator_client.delete(f"{SERVICE_URL}{service_id}/").status_code == 405
