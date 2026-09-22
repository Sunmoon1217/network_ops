"""设备组与配置属主测试。

覆盖：
- 无组设备、ha 组的设备都以自身为配置属主
- stack 组的备机归属组内主设备
- stack 组缺主设备时回退到自身
- 备机查询配置时返回主设备的配置（视图层重定向）
- 备机的 DeviceConfig 不触发解析
"""

import pytest
from rest_framework.test import APIClient

from assets.models import Device, DeviceConfig, DeviceGroup, DeviceGroupMember
from ingest.config_owner import resolve_config_owner


def _device(hostname: str) -> Device:
    return Device.objects.create(hostname=hostname, device_type="switch")


def _stack_group(name: str, master: Device, backup: Device) -> DeviceGroup:
    group = DeviceGroup.objects.create(name=name, group_type="stack")
    DeviceGroupMember.objects.create(group=group, device=master, device_role="master")
    DeviceGroupMember.objects.create(group=group, device=backup, device_role="backup")
    return group


@pytest.mark.django_db
def test_owner_is_self_without_group():
    """没有加入任何组的设备，配置属主是自己"""
    device = _device("dg-solo")
    assert resolve_config_owner(device).pk == device.pk


@pytest.mark.django_db
def test_stack_backup_resolves_to_master():
    """stack 组：主机属主是自己，备机归属主机"""
    master, backup = _device("dg-m"), _device("dg-b")
    _stack_group("stack-1", master, backup)

    assert resolve_config_owner(master).pk == master.pk
    assert resolve_config_owner(backup).pk == master.pk


@pytest.mark.django_db
def test_ha_group_is_not_shared():
    """ha 组不共享配置，两台设备各自是自身的属主"""
    device_a, device_b = _device("dg-ha-a"), _device("dg-ha-b")
    group = DeviceGroup.objects.create(name="ha-1", group_type="ha")
    DeviceGroupMember.objects.create(group=group, device=device_a, device_role="master")
    DeviceGroupMember.objects.create(group=group, device=device_b, device_role="backup")

    assert resolve_config_owner(device_a).pk == device_a.pk
    assert resolve_config_owner(device_b).pk == device_b.pk


@pytest.mark.django_db
def test_stack_without_master_falls_back_to_self():
    """stack 组里没有主设备时，备机回退为自身（不报错、不递归）"""
    device = _device("dg-nomaster")
    group = DeviceGroup.objects.create(name="stack-2", group_type="stack")
    DeviceGroupMember.objects.create(group=group, device=device, device_role="backup")

    assert resolve_config_owner(device).pk == device.pk


@pytest.mark.django_db
def test_backup_config_query_redirects_to_master():
    """备机查询配置接口时返回主设备的配置记录"""
    master, backup = _device("dg-q-m"), _device("dg-q-b")
    _stack_group("stack-q", master, backup)
    DeviceConfig.objects.bulk_create(
        [DeviceConfig(device=master, git_commit_hash="a" * 40, config_json={"interfaces": []})]
    )

    client = APIClient()
    master_rows = client.get("/api/assets/device-configs/", {"device": master.pk}).json()["results"]
    backup_rows = client.get("/api/assets/device-configs/", {"device": backup.pk}).json()["results"]
    master_ids = [row["id"] for row in master_rows]
    backup_ids = [row["id"] for row in backup_rows]

    assert len(master_ids) == 1
    assert master_ids == backup_ids


@pytest.mark.django_db
def test_backup_device_config_is_not_parsed(caplog):
    """备机的 DeviceConfig 不触发解析（config_json 保持为空）"""
    master, backup = _device("dg-skip-m"), _device("dg-skip-b")
    _stack_group("stack-skip", master, backup)

    config = DeviceConfig.objects.create(device=backup, git_commit_hash="b" * 40)
    config.refresh_from_db()

    assert not config.config_json
    assert "跳过解析" in caplog.text
