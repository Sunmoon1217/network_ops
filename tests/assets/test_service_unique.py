"""Service 唯一约束与拆行的测试。

约束是 ``UniqueConstraint(fields=["device", "name", "protocol", "port", "port2"])``
（自然键）：一个服务名允许多行端口定义——tcp 22 与 udp 53 各一行，不再合并进一条
protocol/port（2026-09 修复：合并会把 udp 语义压丢、port 变成 "22,53" 脏值）。
完全相同的自然键仍然拒绝；跨设备同名照旧合法。ServiceSaver 按自然键做差量。
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
def test_same_name_different_ports_allowed_same_device():
    """同设备同名**不同端口定义**必须允许——这是 tcp22/udp53 拆两行的前提"""
    fw = Device.objects.create(hostname="_t_svc_split", device_type="firewall")

    Service.objects.create(device=fw, name="X", protocol="tcp", port="22")
    Service.objects.create(device=fw, name="X", protocol="udp", port="53")

    assert Service.objects.filter(device=fw, name="X").count() == 2


@pytest.mark.django_db
def test_duplicate_natural_key_still_rejected():
    """同一设备内**完全相同的自然键**仍然不允许（唯一性从 name 收敛到了自然键）"""
    fw = Device.objects.create(hostname="_t_svc_dup", device_type="firewall")
    Service.objects.create(device=fw, name="HTTP", protocol="tcp", port="80")

    with pytest.raises(IntegrityError), transaction.atomic():
        Service.objects.create(device=fw, name="HTTP", protocol="tcp", port="80")


@pytest.mark.django_db
def test_service_saver_splits_multi_row_definition():
    """核心修复：同名多行定义 → ServiceSaver 逐行落库，不合并

    形态是 hillstone 动态组的产出 ``{名字: [行, 行]}``——tcp 22 与 udp 53
    必须各占一行（protocol/port 不许互相挤压）。
    """
    fw = Device.objects.create(hostname="_t_svc_rows", device_type="firewall")
    saver = ServiceSaver()

    payload = {
        "services": {
            "X-wrapper": [
                {"protocol": "tcp", "port_type": "dst", "port": "22"},
                {"protocol": "udp", "port_type": "dst", "port": "53"},
            ]
        }
    }
    created, updated = saver.save(fw, payload)

    assert (created, updated) == (2, 0)
    rows = {(r.protocol, r.port) for r in Service.objects.filter(device=fw, name="X-wrapper")}
    assert rows == {("tcp", "22"), ("udp", "53")}

    # 差量：第二次喂 tcp22 + tcp443（udp53 被配置删除）→ 建 443、删 53、复用 22（pk 不动）
    pk_22 = Service.objects.get(device=fw, name="X-wrapper", protocol="tcp", port="22").pk
    saver.save(
        fw,
        {
            "services": {
                "X-wrapper": [
                    {"protocol": "tcp", "port": "22"},
                    {"protocol": "tcp", "port": "443"},
                ]
            }
        },
    )
    assert Service.objects.filter(device=fw, name="X-wrapper").count() == 2
    assert Service.objects.get(device=fw, name="X-wrapper", protocol="tcp", port="22").pk == pk_22
    assert not Service.objects.filter(device=fw, name="X-wrapper", protocol="udp").exists()


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
