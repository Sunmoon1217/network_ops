"""DeviceAccount Saver 测试。

只覆盖 H3C 的 ``local_users`` 产出；``ssh`` / ``roles`` / A10 的 ``account``
不属于账号数据，不在 Saver 的 key 里。
"""

import pytest

from assets.models import Device, DeviceAccount
from ingest.savers.account import DeviceAccountSaver


@pytest.mark.django_db
def test_local_user_saved_from_single_dict():
    """TTP 单条命中给的是 dict，也要能入库"""
    device = Device.objects.create(hostname="_t_acc_sw", device_type="switch")
    parsed = {
        "local_users": {
            "username": "ingest",
            "user_class": "manage",
            "password": "$h$abc",
            "service_type": ["ssh", "terminal"],
            "role": ["network-admin"],
        }
    }

    assert DeviceAccountSaver().save(device, parsed) == (1, 0)

    account = DeviceAccount.objects.get(device=device)
    assert account.username == "ingest"
    assert account.privilege == "admin"
    assert account.auth_type == "password"
    assert "service-type: ssh terminal" in account.description
    assert "role: network-admin" in account.description


@pytest.mark.django_db
def test_local_user_class_maps_to_privilege():
    """H3C 的 class manage / network / read 映射到三种权限级别"""
    device = Device.objects.create(hostname="_t_acc_cls", device_type="switch")
    parsed = {
        "local_users": [
            {"username": "u_admin", "user_class": "manage"},
            {"username": "u_op", "user_class": "network"},
            {"username": "u_ro", "user_class": "read"},
        ]
    }

    assert DeviceAccountSaver().save(device, parsed) == (3, 0)

    assert DeviceAccount.objects.get(device=device, username="u_admin").privilege == "admin"
    assert DeviceAccount.objects.get(device=device, username="u_op").privilege == "operator"
    assert DeviceAccount.objects.get(device=device, username="u_ro").privilege == "readonly"


@pytest.mark.django_db
def test_privilege_falls_back_to_user_role():
    """部分版本没有 class，改用 authorization-attribute user-role 表达级别"""
    device = Device.objects.create(hostname="_t_acc_role", device_type="switch")
    parsed = {
        "local_users": [
            {"username": "u1", "role": ["network-admin"]},
            {"username": "u2", "role": ["read"]},
        ]
    }

    assert DeviceAccountSaver().save(device, parsed) == (2, 0)

    assert DeviceAccount.objects.get(device=device, username="u1").privilege == "admin"
    assert DeviceAccount.objects.get(device=device, username="u2").privilege == "readonly"


@pytest.mark.django_db
def test_auth_type_defaults_to_ssh_key_without_password():
    """配置里没有 password（走密钥）时认证方式应是 ssh-key"""
    device = Device.objects.create(hostname="_t_acc_key", device_type="switch")

    assert DeviceAccountSaver().save(device, {"local_users": {"username": "keyuser"}}) == (1, 0)

    assert DeviceAccount.objects.get(device=device).auth_type == "ssh-key"


@pytest.mark.django_db
def test_skips_records_without_username_and_is_idempotent():
    """缺 username 的记录跳过；同一用户重复入库是更新而非新增"""
    device = Device.objects.create(hostname="_t_acc_idem", device_type="switch")
    saver = DeviceAccountSaver()

    assert saver.save(device, {"local_users": [{"user_class": "manage"}, {"username": "dup"}]}) == (1, 0)
    assert saver.save(device, {"local_users": {"username": "dup", "user_class": "read"}}) == (0, 1)
    assert DeviceAccount.objects.filter(device=device).count() == 1
    assert DeviceAccount.objects.get(device=device).privilege == "readonly"


@pytest.mark.django_db
def test_empty_payload_is_noop():
    device = Device.objects.create(hostname="_t_acc_empty", device_type="switch")
    assert DeviceAccountSaver().save(device, {}) == (0, 0)
    assert DeviceAccount.objects.filter(device=device).count() == 0
