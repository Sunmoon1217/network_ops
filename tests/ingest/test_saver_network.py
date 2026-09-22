"""Vlan / SnmpConfig / Route 三个 Saver 的测试。

这三个模型原本是裸 models.Model，改为继承 ConfigBase 后统一走
``BaseSaver.upsert``（序列化器）入库。模板产出因厂商而异，测试用真实解析产出驱动。
"""

import pytest

from assets.models import Device, Route, SnmpConfig, Vlan, Vrf
from ingest.parsers.factory import ParserFactory
from ingest.savers.network import SnmpConfigSaver, VlanSaver
from ingest.savers.routing import RouteSaver


def _parse(vendor: str, device_type: str, cfg: str) -> dict:
    return ParserFactory.get_parser_by_keys(vendor, device_type).parse(cfg)


# ---------- Vlan ----------


@pytest.mark.django_db
def test_vlan_from_h3c_output():
    device = Device.objects.create(hostname="_t_vlan_sw", device_type="switch")
    parsed = _parse("H3C", "switch", "vlan 10\nvlan 20\n")

    assert VlanSaver().save(device, parsed) == (2, 0)

    assert Vlan.objects.filter(device=device).count() == 2
    assert set(Vlan.objects.filter(device=device).values_list("vid", flat=True)) == {10, 20}


@pytest.mark.django_db
def test_vlan_is_idempotent_and_skips_records_without_vid():
    device = Device.objects.create(hostname="_t_vlan_idem", device_type="switch")
    saver = VlanSaver()

    assert saver.save(device, {"vlans": {"vlan_id": "100", "vlan_name": "X"}}) == (1, 0)
    assert saver.save(device, {"vlans": {"vlan_id": "100", "vlan_name": "X"}}) == (0, 1)
    assert saver.save(device, {"vlans": [{"vlan_name": "没有 id"}]}) == (0, 0)

    assert Vlan.objects.filter(device=device).count() == 1
    assert Vlan.objects.get(device=device).vid == 100


# ---------- SnmpConfig ----------


@pytest.mark.django_db
def test_snmp_from_huawei_output():
    """Huawei / H3C router 形态：community + access_type + host_ip"""
    device = Device.objects.create(hostname="_t_snmp_hw", device_type="switch")
    parsed = _parse("Huawei", "switch", "snmp-agent community read public\nsnmp-agent host 10.0.0.9 public\n")

    assert SnmpConfigSaver().save(device, parsed) == (1, 0)

    snmp = SnmpConfig.objects.get(device=device)
    assert snmp.community_read == "public"
    assert snmp.trap_enabled is True
    assert str(snmp.trap_server) == "10.0.0.9"


@pytest.mark.django_db
def test_snmp_write_community_goes_to_write_field():
    """access_type 为 write 时写进 community_write"""
    device = Device.objects.create(hostname="_t_snmp_w", device_type="router")
    parsed = _parse("H3C", "router", " snmp-agent community write private\n snmp-agent host 10.0.0.8 private\n")

    SnmpConfigSaver().save(device, parsed)

    snmp = SnmpConfig.objects.get(device=device)
    assert snmp.community_write == "private"
    assert snmp.community_read == ""


@pytest.mark.django_db
def test_snmp_is_single_record_per_device():
    """SnmpConfig 是每设备一条：第二次入库是更新而非新增"""
    device = Device.objects.create(hostname="_t_snmp_one", device_type="switch")
    saver = SnmpConfigSaver()
    parsed = _parse("Huawei", "switch", "snmp-agent community read public\n")

    assert saver.save(device, parsed) == (1, 0)
    assert saver.save(device, parsed) == (0, 1)
    assert SnmpConfig.objects.filter(device=device).count() == 1


@pytest.mark.django_db
def test_snmp_normalizes_version_and_empty_payload_is_noop():
    device = Device.objects.create(hostname="_t_snmp_ver", device_type="switch")
    saver = SnmpConfigSaver()

    assert saver.save(device, {"snmp": {"version": "2c"}}) == (1, 0)
    assert SnmpConfig.objects.get(device=device).version == "v2c"
    assert saver.save(device, {}) == (0, 0)


# ---------- Route ----------


@pytest.mark.django_db
def test_route_creates_default_vrf_and_matches_device():
    device = Device.objects.create(hostname="_t_route_hw", device_type="switch")
    parsed = _parse("Huawei", "switch", "ip route-static 10.1.0.0 255.255.0.0 10.0.0.2\n")

    assert RouteSaver().save(device, parsed) == (1, 0)

    route = Route.objects.get(device=device)
    assert route.destination == "10.1.0.0/16"
    assert str(route.nexthop) == "10.0.0.2"
    assert route.protocol == "static"
    assert route.vrf.name == "default"
    # 继承来的 device 必须与 vrf.device 一致（与数据迁移的回填口径相同）
    assert route.vrf.device_id == route.device_id


@pytest.mark.django_db
def test_route_accepts_cisco_fields_and_subnet_mask_key():
    """cisco 的产出带 interface_name 与 metric；Maipu / Ruijie 用 subnet_mask"""
    device = Device.objects.create(hostname="_t_route_cisco", device_type="firewall")
    parsed = _parse("Cisco", "firewall", "route outside 10.3.0.0 255.255.0.0 10.0.0.4 1\n")

    assert RouteSaver().save(device, parsed) == (1, 0)

    route = Route.objects.get(device=device)
    assert route.destination == "10.3.0.0/16"
    assert route.interface == "outside"
    assert route.metric == 1


@pytest.mark.django_db
def test_route_reuses_existing_default_vrf():
    device = Device.objects.create(hostname="_t_route_vrf", device_type="switch")
    vrf = Vrf.objects.create(device=device, name="default")
    parsed = {"static_routes": {"destination_network": "10.0.0.0", "mask": "255.0.0.0", "next_hop": "1.1.1.1"}}

    RouteSaver().save(device, parsed)

    assert Vrf.objects.filter(device=device).count() == 1
    assert Route.objects.get(device=device).vrf_id == vrf.pk  # type: ignore


@pytest.mark.django_db
def test_route_is_idempotent():
    device = Device.objects.create(hostname="_t_route_idem", device_type="switch")
    saver = RouteSaver()
    parsed = {"static_routes": {"destination_network": "10.0.0.0", "mask": "255.0.0.0", "next_hop": "1.1.1.1"}}

    assert saver.save(device, parsed) == (1, 0)
    assert saver.save(device, parsed) == (0, 1)
    assert Route.objects.filter(device=device).count() == 1


@pytest.mark.django_db
def test_duplicate_vlan_in_one_config_is_collapsed():
    """同一份配置里重复的 vlan：批量 upsert 要去重，不能两条一起进 bulk_create。

    逐条 upsert 时是「后来的覆盖先前的」，批量化后必须显式去重，否则直接撞
    (device, vid) 唯一约束。
    """
    device = Device.objects.create(hostname="_t_vlan_dup", device_type="switch")

    assert VlanSaver().save(
        device, {"vlans": [{"vlan_id": "30", "vlan_name": "先"}, {"vlan_id": "30", "vlan_name": "后"}]}
    ) == (
        1,
        0,
    )

    vlan = Vlan.objects.get(device=device, vid=30)
    assert vlan.name == "后"
    assert Vlan.objects.filter(device=device).count() == 1
