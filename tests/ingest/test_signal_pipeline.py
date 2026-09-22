"""配置入库链路的回归测试。

覆盖「DeviceConfig 保存 → 信号 → 解析 → Saver 写库」这条链上查出过的缺陷：

- 4 个老 Saver 在"只解析出 1 条"（TTP 单条命中返回 dict）时不应崩溃
- ``get_savers_for_config`` 必须把命中同一 Saver 的多个 key 一起返回
- 设备没设型号时 ``get_parser`` 应抛 ``ValueError``（而不是 ``AttributeError``）
- commit 不存在时 ``get_config`` 应返回 ``None``（而不是抛 ``BadName``）
- 同一 commit 重复导入不应清空已经解析好的 ``config_json``
"""

import pytest

from assets.models import Device, DeviceConfig, DeviceModel, Service, Vendor, Vlan, Vrf
from ingest.config_repo import get_config
from ingest.parsers.factory import ParserFactory
from ingest.savers.firewall import ServiceSaver
from ingest.savers.interface import InterfaceSaver
from ingest.savers.lb import LBSnatSaver
from ingest.savers.registry import get_savers_for_config
from ingest.savers.routing import VrfSaver

# ---------- 单条命中（dict）不应崩溃 ----------


@pytest.mark.django_db
def test_switch_savers_accept_single_dict_payload():
    """TTP 只解析到一条时给的是 dict，InterfaceSaver / VrfSaver 不能崩"""
    device = Device.objects.create(hostname="_t_dict_sw", device_type="switch")

    assert InterfaceSaver().save(device, {"interfaces": {"interface": "GE1/0/1", "mode": "access"}}) == (1, 0)
    assert VrfSaver().save(device, {"vpn_instances": {"vrf": "VPN-A"}}) == (1, 0)

    assert device.interface_set.count() == 1  # type: ignore
    assert Vrf.objects.get(device=device).name == "VPN-A"


@pytest.mark.django_db
def test_firewall_and_slb_savers_accept_single_dict_payload():
    """ServiceSaver / LBSnatSaver 同理"""
    firewall = Device.objects.create(hostname="_t_dict_fw", device_type="firewall")
    assert ServiceSaver().save(firewall, {"services": {"name": "HTTP", "protocol": "tcp"}}) == (1, 0)
    assert Service.objects.get(device=firewall).name == "HTTP"

    slb = Device.objects.create(hostname="_t_dict_slb", device_type="slb")
    assert LBSnatSaver().save(slb, {"snat": {"name": "snat1", "address": "1.1.1.1"}}) == (1, 0)


# ---------- 多 key 聚合 ----------


def test_get_savers_for_config_groups_keys_of_same_saver():
    """PolicySaver 覆盖 policies / acl / rules，命中多个 key 时要一起返回"""
    savers = get_savers_for_config("firewall", {"acl": [{"rule_id": "1"}], "rules": [{"rule_id": "2"}]})

    by_saver = {type(saver).__name__: keys for keys, saver in savers}
    assert by_saver["PolicySaver"] == ["acl", "rules"]


def test_get_savers_for_config_skips_unregistered_keys():
    """没有 Saver 的 key 不应出现在结果里"""
    savers = get_savers_for_config("switch", {"hostname": "x", "version": "y", "vlans": []})

    assert [keys for keys, _ in savers] == [["vlans"]]


# ---------- 可诊断性 ----------


def test_get_parser_without_device_model_raises_value_error():
    """设备没设型号时应抛 ValueError，调用方才能按"无匹配解析器"处理"""
    device = Device(hostname="_t_no_model", device_type="switch")

    with pytest.raises(ValueError, match="未设置型号"):
        ParserFactory.get_parser(device)


def test_get_config_returns_none_for_unknown_commit():
    """commit 在仓库里不存在时返回 None，而不是抛 gitdb 的 BadName"""
    assert get_config("不存在的设备", "deadbeef") is None


# ---------- 重复导入不清空解析结果 ----------


@pytest.mark.django_db
def test_reimport_same_commit_keeps_config_json():
    """同一 commit 重复导入必须保留已有 config_json（否则解析结果永久丢失）"""
    device = Device.objects.create(hostname="_t_reimport", device_type="switch")
    original = {"vlans": [{"vlan_id": "1"}]}
    record = DeviceConfig.objects.create(device=device, git_commit_hash="aaa111", config_json=original)

    _, created = DeviceConfig.objects.get_or_create(
        device=device, git_commit_hash="aaa111", defaults={"config_json": {}}
    )
    record.refresh_from_db()

    assert created is False
    assert record.config_json == original


# ---------- 端到端：第 8 步之后要走到第 9 步 ----------


@pytest.mark.django_db
def test_signal_parses_then_dispatches_to_savers(monkeypatch):
    """整条链：config_json 为空 → 读 Git → 解析 → 写回 → 分发给 Saver

    用 monkeypatch 替换 get_config，避免测试依赖真实的 Git 仓库内容。
    """
    raw = "sysname E2E\nvlan 10\nvlan 20\n"
    monkeypatch.setattr("ingest.config_repo.get_config", lambda hostname, commit=None: raw)

    vendor = Vendor.objects.create(name="H3C")
    model = DeviceModel.objects.create(name="S5560X", vendor=vendor)
    device = Device.objects.create(hostname="_t_e2e_sw", device_type="switch", device_model=model)

    config = DeviceConfig.objects.create(device=device, git_commit_hash="e2e0001", config_json={})
    config.refresh_from_db()

    # 解析结果写回了 config_json
    assert "vlans" in config.config_json
    # Saver 也真的跑了
    assert Vlan.objects.filter(device=device).count() == 2


@pytest.mark.django_db
def test_signal_is_idempotent_on_reimport(monkeypatch):
    """同一 commit 再次导入（created=False）不重复写入"""
    raw = "sysname E2E\nvlan 10\n"
    monkeypatch.setattr("ingest.config_repo.get_config", lambda hostname, commit=None: raw)

    vendor = Vendor.objects.create(name="H3C")
    model = DeviceModel.objects.create(name="S5560X", vendor=vendor)
    device = Device.objects.create(hostname="_t_e2e_idem", device_type="switch", device_model=model)

    DeviceConfig.objects.create(device=device, git_commit_hash="e2e0002", config_json={})
    assert Vlan.objects.filter(device=device).count() == 1

    DeviceConfig.objects.get_or_create(device=device, git_commit_hash="e2e0002", defaults={"config_json": {}})
    assert Vlan.objects.filter(device=device).count() == 1
