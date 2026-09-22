"""Service 唯一约束按设备隔离的测试。

约束是 ``UniqueConstraint(fields=["device", "name"])``：不同设备可以有同名服务，
同一设备内不允许重名——这正是 ServiceSaver / PolicySaver 按 ``(device, name)``
做 upsert 所依赖的前提。改成这样的原因见 models.Service.Meta 的注释。
"""

import pytest
from django.db import IntegrityError, transaction

from assets.models import Device, Service
from ingest.savers.firewall import ServiceSaver


@pytest.mark.django_db
def test_same_service_name_on_different_devices():
    """两台设备各有一个同名服务都应成功（原先 name 全局唯一时这里会撞约束）"""
    fw1 = Device.objects.create(hostname="_t_svc_fw1", device_type="firewall")
    fw2 = Device.objects.create(hostname="_t_svc_fw2", device_type="firewall")

    Service.objects.create(device=fw1, name="HTTP", protocol="tcp", port="80")
    Service.objects.create(device=fw2, name="HTTP", protocol="tcp", port="8080")

    assert Service.objects.filter(name="HTTP").count() == 2


@pytest.mark.django_db
def test_same_name_on_same_device_is_still_rejected():
    """同一设备内重名仍然不允许"""
    fw = Device.objects.create(hostname="_t_svc_dup", device_type="firewall")
    Service.objects.create(device=fw, name="HTTP", protocol="tcp")

    with pytest.raises(IntegrityError), transaction.atomic():
        Service.objects.create(device=fw, name="HTTP", protocol="tcp")


@pytest.mark.django_db
def test_service_saver_keeps_devices_isolated():
    """ServiceSaver 按 (device, name) upsert，两台设备的同名服务互不覆盖"""
    fw1 = Device.objects.create(hostname="_t_svc_s1", device_type="firewall")
    fw2 = Device.objects.create(hostname="_t_svc_s2", device_type="firewall")
    saver = ServiceSaver()

    assert saver.save(fw1, {"services": {"name": "HTTP", "protocol": "tcp", "port": "80"}}) == (1, 0)
    assert saver.save(fw2, {"services": {"name": "HTTP", "protocol": "tcp", "port": "8080"}}) == (1, 0)

    assert Service.objects.filter(name="HTTP").count() == 2
    assert Service.objects.get(device=fw1, name="HTTP").port == "80"
    assert Service.objects.get(device=fw2, name="HTTP").port == "8080"


@pytest.mark.django_db
def test_policy_saver_can_reference_same_service_on_two_devices():
    """PolicySaver 也会 get_or_create 服务，两台设备各自引用同名服务不应冲突"""
    from assets.models import Policy
    from ingest.savers.firewall import PolicySaver

    saver = PolicySaver()
    for index, hostname in enumerate(("_t_pol_s1", "_t_pol_s2"), start=1):
        device = Device.objects.create(hostname=hostname, device_type="firewall")
        parsed = {
            "rules": {
                "rule_id": str(index),
                "action": "permit",
                "service": ["HTTPS"],
                "name": f"rule-{index}",
            }
        }
        assert saver.save(device, parsed) == (1, 0)

    assert Service.objects.filter(name="HTTPS").count() == 2
    assert Policy.objects.count() == 2
