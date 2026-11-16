"""配置模型的运行时枚举契约：purge_configs 靠它决定清哪些表。

拆分切片 1 只有 Vlan 进了 configs；切片 2 后 25 个 ConfigBase 子类（含改为继承基类的
ArpMac）全部搬完。集合写死在这里，多一个少一个都让本用例失败——静默漏枚举意味着
配置行没人清，多枚举意味着清掉不该清的表。
"""

import configs.models as cm
from configs.models import ConfigBase, DeviceConfig

EXPECTED_SUBCLASSES = {
    "AddressBook",
    "ArpMac",
    "DeviceAccount",
    "GtmDatacenter",
    "GtmPool",
    "GtmServer",
    "GtmVServer",
    "GtmWideip",
    "Interface",
    "LtmIRule",
    "LtmPersist",
    "LtmPool",
    "LtmPoolMember",
    "LtmProfile",
    "LtmSNAT",
    "LtmVirtualServer",
    "NatRule",
    "NtpConfig",
    "Policy",
    "Route",
    "Service",
    "SnmpConfig",
    "SyslogConfig",
    "Vlan",
    "Vrf",
}


def test_configbase_subclasses_exact_set():
    """25 个子类一个不多一个不少（ArpMac 改继承后计入）。"""
    assert {cls.__name__ for cls in ConfigBase.__subclasses__()} == EXPECTED_SUBCLASSES


def test_all_config_rows_belong_to_configs_app():
    """枚举到的类全部属于 configs——旧 assets 里还留子类说明拆分没做完。"""
    for cls in ConfigBase.__subclasses__():
        assert cls._meta.app_label == "configs", f"{cls.__name__} 还在别的 app"


def test_device_config_not_enumerated():
    """配置快照不继承 ConfigBase，不能被 purge 的配置行清理带走。"""
    assert DeviceConfig not in ConfigBase.__subclasses__()
    assert DeviceConfig._meta.app_label == "configs"


def test_configs_package_exports_every_model():
    """包出口覆盖全部模型，调用方不必知道模型定义在哪个子模块。"""
    for name in EXPECTED_SUBCLASSES | {"DeviceConfig"}:
        assert getattr(cm, name)._meta.app_label == "configs"
