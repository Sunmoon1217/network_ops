"""设备组配置合并公共层（``analysis.api.group_merge``）测试。

覆盖组划分口径：主备（``ha`` / ``failover``）参与合并、单机与堆叠不参与、
一台设备多组时取第一个、未入组设备各自单机组、按组键/组名/设备收窄。
"""

import pytest

from analysis.api.group_merge import HA_GROUP_TYPES, resolve_groups
from assets.models import Device, DeviceGroup, DeviceGroupMember


def _device(hostname: str, device_type: str = "slb") -> Device:
    return Device.objects.create(hostname=hostname, device_type=device_type)


def _group(name: str, group_type: str, devices: list[Device]) -> DeviceGroup:
    group = DeviceGroup.objects.create(name=name, group_type=group_type)
    for device in devices:
        DeviceGroupMember.objects.create(group=group, device=device)
    return group


@pytest.mark.django_db
def test_ha_and_failover_groups_merge_but_single_and_stack_do_not():
    """ha / failover 组的成员合并成一组；single / stack 组各自拆成单机组。"""
    a, b = _device("slb-a"), _device("slb-b")
    c, d, e = _device("single-x"), _device("stack-m"), _device("stack-b")
    ha = _group("ha-pair", "ha", [a, b])
    _group("single-x", "single", [c])
    _group("stack", "stack", [d, e])

    groups = resolve_groups("slb", HA_GROUP_TYPES)
    by_name = {group.name: group for group in groups}

    assert by_name["ha-pair"].key == f"group-{ha.pk}"
    assert [device.hostname for device in by_name["ha-pair"].devices] == ["slb-a", "slb-b"]
    # 堆叠与单机组不参与合并 → 两台堆叠设备各自成为单机组
    assert by_name["stack-m"].devices == [d]
    assert by_name["stack-b"].devices == [e]
    assert by_name["single-x"].devices == [c]


@pytest.mark.django_db
def test_device_in_multiple_groups_takes_first_by_name_then_id():
    """一台设备落在多个命中组时，按（组名, id）取第一个，其余忽略。"""
    device = _device("slb-only")
    _group("zeta", "ha", [device])
    alpha = _group("alpha", "failover", [device])

    groups = resolve_groups("slb", HA_GROUP_TYPES)
    assert [group.name for group in groups] == ["alpha"]
    assert groups[0].key == f"group-{alpha.pk}"


@pytest.mark.django_db
def test_device_type_filter_isolates():
    """只取指定 device_type 的设备：防火墙的 ha 组不影响 slb 的划分。"""
    fw_a, fw_b = _device("fw-a", "firewall"), _device("fw-b", "firewall")
    _group("fw-ha", "ha", [fw_a, fw_b])

    firewall_groups = resolve_groups("firewall", HA_GROUP_TYPES)
    slb_groups = resolve_groups("slb", HA_GROUP_TYPES)

    assert [device.hostname for device in firewall_groups[0].devices] == ["fw-a", "fw-b"]
    assert slb_groups == []  # 没有 slb 设备


@pytest.mark.django_db
def test_narrow_by_group_key_group_name_and_device_id():
    """收窄：按组键 / 组名 / 设备 id 都能定位到同一组。"""
    a, b, solo = _device("fw-a", "firewall"), _device("fw-b", "firewall"), _device("fw-solo", "firewall")
    ha = _group("fw-pair", "ha", [a, b])

    assert [g.name for g in resolve_groups("firewall", HA_GROUP_TYPES, group_key=f"group-{ha.pk}")] == ["fw-pair"]
    assert [g.name for g in resolve_groups("firewall", HA_GROUP_TYPES, group_key="fw-pair")] == ["fw-pair"]
    assert [g.name for g in resolve_groups("firewall", HA_GROUP_TYPES, device_id=b.pk)] == ["fw-pair"]
    assert [g.name for g in resolve_groups("firewall", HA_GROUP_TYPES, device_id=solo.pk)] == ["fw-solo"]
    assert resolve_groups("firewall", HA_GROUP_TYPES, group_key="nope") == []
