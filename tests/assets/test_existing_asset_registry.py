"""存量资产登记（T4）的契约测试。

锁住四件事：三类来源都登记、重复执行幂等、改名同步且 `ci_id` 不变、试算不写库。
映射表本身还有两条硬约束：`(source_type, source_id)` 唯一、`ci_type` 必须与来源一致。
"""

import pytest

from assets.models import CIObjectLink, CIType, ConfigurationItem, Device, IPAddress, Subnet
from assets.services.existing_asset_registry import register_existing_assets


def _seed() -> None:
    Device.objects.create(hostname="SW-01", device_type="switch")
    Subnet.objects.create(network="10.0.0.0/24")
    IPAddress.objects.create(ip_address="10.0.0.1")


@pytest.mark.django_db
def test_registers_all_three_kinds():
    """设备 / 网段 / IP 各登记一条 CI，名称取各自的名字字段。"""
    _seed()
    result = register_existing_assets()

    assert {kind: stats.created for kind, stats in result.items()} == {
        CIType.DEVICE: 1,
        CIType.IP_ADDRESS: 1,
        CIType.SUBNET: 1,
    }
    assert ConfigurationItem.objects.count() == 3
    assert CIObjectLink.objects.count() == 3

    by_type = {ci.ci_type: ci.name for ci in ConfigurationItem.objects.all()}
    assert by_type == {CIType.DEVICE: "SW-01", CIType.SUBNET: "10.0.0.0/24", CIType.IP_ADDRESS: "10.0.0.1"}


@pytest.mark.django_db
def test_second_run_is_idempotent():
    """重复执行不新增、不改 ci_id：按 (source_type, source_id) 命中已有映射。"""
    _seed()
    register_existing_assets()
    ids_before = set(ConfigurationItem.objects.values_list("ci_id", flat=True))

    result = register_existing_assets()

    assert all(stats.created == 0 and stats.updated == 0 for stats in result.values())
    assert ConfigurationItem.objects.count() == 3
    assert set(ConfigurationItem.objects.values_list("ci_id", flat=True)) == ids_before


@pytest.mark.django_db
def test_rename_updates_name_but_keeps_ci_id():
    """源记录改名 → 重跑只更新名字，锚点不变（T15 的 Zabbix 标签不能失效）。"""
    device = Device.objects.create(hostname="SW-01", device_type="switch")
    register_existing_assets()
    link = CIObjectLink.objects.get(source_type=CIType.DEVICE, source_id=device.pk)
    ci_id = link.ci.ci_id

    Device.objects.filter(pk=device.pk).update(hostname="SW-01-RENAMED")
    result = register_existing_assets(kinds=[CIType.DEVICE])

    assert result[CIType.DEVICE].updated == 1
    link.refresh_from_db()
    assert link.ci.ci_id == ci_id
    assert link.ci.name == "SW-01-RENAMED"


@pytest.mark.django_db
def test_kind_filter_only_touches_requested_type():
    """`--type device` 只登记设备，网段 / IP 不受影响。"""
    _seed()
    result = register_existing_assets(kinds=[CIType.DEVICE])

    assert list(result) == [CIType.DEVICE]
    assert ConfigurationItem.objects.filter(ci_type=CIType.DEVICE).count() == 1
    assert ConfigurationItem.objects.count() == 1


@pytest.mark.django_db
def test_dry_run_writes_nothing():
    """试算只统计，不落 CI 也不落映射。"""
    _seed()
    result = register_existing_assets(dry_run=True)

    assert sum(stats.created for stats in result.values()) == 3
    assert ConfigurationItem.objects.count() == 0
    assert CIObjectLink.objects.count() == 0


@pytest.mark.django_db
def test_unknown_kind_is_rejected():
    """未知类型直接报错，不静默跳过（拼错 `ip` 而不是 `ip_address` 要能发现）。"""
    with pytest.raises(ValueError, match="不支持的存量资产类型"):
        register_existing_assets(kinds=["ip"])


@pytest.mark.django_db
def test_link_rejects_mismatched_ci_type():
    """映射的 ci_type 与来源不一致时，save() 必须拦住（兜住 ORM 直写）。"""
    ci = ConfigurationItem.objects.create(ci_type=CIType.SUBNET, name="10.0.0.0/24")
    with pytest.raises(ValueError, match="要求 ci_type"):
        CIObjectLink.objects.create(ci=ci, source_type=CIType.DEVICE, source_id=1)
