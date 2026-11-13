"""软资产归并（T4）的契约测试：GTM → DomainAsset、LTM → LoadBalancerService。"""

import pytest

from assets.models import (
    ConfigBase,
    Device,
    DomainAsset,
    GtmPool,
    GtmServer,
    GtmVServer,
    GtmWideip,
    LoadBalancerService,
    LtmPoolMember,
    LtmVirtualServer,
)
from assets.services.soft_asset_sync import (
    lb_asset_key,
    normalize_fqdn,
    sync_domain_assets,
    sync_load_balancer_services,
    sync_soft_assets,
)


def _device(hostname: str, device_type: str) -> Device:
    return Device.objects.create(hostname=hostname, device_type=device_type)


def _gtm_wideip(device: Device, name: str, rtype: str = "A", lb_mode: str = "round-robin", ttl: int = 30) -> GtmWideip:
    """一台 GTM 上的一条完整链：wideip → pool → vserver。"""
    server = GtmServer.objects.create(device=device, name="srv1")
    GtmVServer.objects.create(server=server, device=device, name="vs1", ip_address="10.0.0.1", port="80")
    GtmPool.objects.create(device=device, name="pool_web", ttl=ttl, fallback_ip="1.1.1.1", members=[{"server": "srv1", "vserver": "vs1"}])
    return GtmWideip.objects.create(device=device, name=name, rtype=rtype, lb_mode=lb_mode, pools=["pool_web"])


def _ltm_service(device: Device, address: str, port: str, members: int = 3) -> LtmVirtualServer:
    for index in range(members):
        LtmPoolMember.objects.create(device=device, pool_name="pool_web", name=f"node{index}", address=f"192.168.1.{index}", port="8080")
    return LtmVirtualServer.objects.create(
        device=device,
        name="vs_web",
        vs_address=address,
        vs_port=port,
        protocol="tcp",
        status="enabled",
        pool="pool_web",
        profiles=["http"],
        rules=["irule_1"],
    )


def test_normalize_fqdn_strips_dot_and_lowercases():
    assert normalize_fqdn("  A.Example.COM.  ") == "a.example.com"


def test_lb_asset_key_uses_hash_separator():
    assert lb_asset_key("10.1.1.10", "443") == "10.1.1.10#443"
    assert lb_asset_key("2001:db8::1", "80") == "2001:db8::1#80"
    assert lb_asset_key("10.1.1.10", "") == "10.1.1.10"


@pytest.mark.django_db
def test_wideip_maps_to_domain_asset():
    _gtm_wideip(_device("gtm-a", "gslb"), "A.Example.COM.")

    stats = sync_domain_assets()

    assert (stats.created, stats.updated, stats.skipped) == (1, 0, 0)
    asset = DomainAsset.objects.get()
    assert asset.fqdn == "a.example.com"
    assert asset.rtypes == ["A"]
    assert asset.ttl == 30
    assert asset.lb_mode == "round-robin"
    assert asset.pools == ["pool_web"]
    assert asset.fallback_ips == ["1.1.1.1"]
    assert asset.vips == ["10.0.0.1#80"]
    assert asset.devices == ["gtm-a"]
    assert asset.inconsistent is False
    assert asset.ci.ci_type == "domain"


@pytest.mark.django_db
def test_same_fqdn_across_devices_merges_into_one_asset():
    """跨设备是同一个域名资产：记录类型并集、设备多值"""
    _gtm_wideip(_device("gtm-a", "gslb"), "a.example.com", rtype="A")
    _gtm_wideip(_device("gtm-b", "gslb"), "a.example.com", rtype="AAAA")

    sync_domain_assets()

    asset = DomainAsset.objects.get()
    assert asset.rtypes == ["A", "AAAA"]
    assert asset.devices == ["gtm-a", "gtm-b"]
    # 两台设备的成员地址相同 → 去重后仍是一个 VIP#port
    assert asset.vips == ["10.0.0.1#80"]


@pytest.mark.django_db
def test_domain_conflict_marks_inconsistent():
    _gtm_wideip(_device("gtm-a", "gslb"), "a.example.com", lb_mode="round-robin")
    _gtm_wideip(_device("gtm-b", "gslb"), "a.example.com", lb_mode="topology")

    sync_domain_assets()

    asset = DomainAsset.objects.get()
    assert asset.inconsistent is True
    assert asset.conflict_fields == ["lb_mode"]


@pytest.mark.django_db
def test_virtual_server_maps_to_load_balancer_asset():
    _ltm_service(_device("slb-a", "slb"), "10.1.1.10", "443")

    stats = sync_load_balancer_services()

    assert (stats.created, stats.skipped) == (1, 0)
    asset = LoadBalancerService.objects.get()
    assert asset.asset_key == "10.1.1.10#443"
    assert (asset.vip, asset.port, asset.protocol, asset.status) == ("10.1.1.10", "443", "tcp", "enabled")
    assert asset.pools == ["pool_web"]
    assert asset.member_count == 3
    assert asset.profiles == ["http"]
    assert asset.rules == ["irule_1"]
    assert asset.devices == ["slb-a"]
    assert asset.ci.ci_type == "load_balancer_service"


@pytest.mark.django_db
def test_ha_pair_member_count_is_not_summed():
    """主备是同一份配置：成员数取单台最大值，不是两台相加"""
    _ltm_service(_device("slb-a", "slb"), "10.1.1.10", "443", members=3)
    _ltm_service(_device("slb-b", "slb"), "10.1.1.10", "443", members=3)

    sync_load_balancer_services()

    asset = LoadBalancerService.objects.get()
    assert asset.member_count == 3
    assert asset.devices == ["slb-a", "slb-b"]


@pytest.mark.django_db
def test_transparent_virtual_server_is_skipped():
    LtmVirtualServer.objects.create(device=_device("slb-a", "slb"), name="vs_transparent", vs_address="", vs_port="80")

    stats = sync_load_balancer_services()

    assert stats.skipped == 1
    assert not LoadBalancerService.objects.exists()


@pytest.mark.django_db
def test_sync_is_idempotent_and_keeps_ci_id():
    _gtm_wideip(_device("gtm-a", "gslb"), "a.example.com")
    _ltm_service(_device("slb-a", "slb"), "10.1.1.10", "443")

    sync_soft_assets()
    domain_ci = DomainAsset.objects.get().ci.ci_id
    service_ci = LoadBalancerService.objects.get().ci.ci_id

    stats = sync_soft_assets()

    assert (stats.created, stats.updated, stats.unchanged) == (0, 0, 2)
    assert DomainAsset.objects.get().ci.ci_id == domain_ci
    assert LoadBalancerService.objects.get().ci.ci_id == service_ci


@pytest.mark.django_db
def test_sync_updates_changed_config():
    device = _device("gtm-a", "gslb")
    _gtm_wideip(device, "a.example.com", ttl=30)
    sync_domain_assets()

    GtmPool.objects.filter(device=device).update(ttl=60)
    stats = sync_domain_assets()

    assert stats.updated == 1
    assert DomainAsset.objects.get().ttl == 60


@pytest.mark.django_db
def test_merged_assets_are_not_config_products():
    _gtm_wideip(_device("gtm-a", "gslb"), "a.example.com")
    _ltm_service(_device("slb-a", "slb"), "10.1.1.10", "443")
    sync_soft_assets()

    assert DomainAsset not in ConfigBase.__subclasses__()
    assert LoadBalancerService not in ConfigBase.__subclasses__()
