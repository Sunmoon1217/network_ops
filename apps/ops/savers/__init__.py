"""数据持久化 Saver 层

导入所有 Saver 模块，__init_subclass__ 自动完成注册。
新增 Saver 步骤：
1. 创建 xxx.py
2. 定义 device_types 和 keys 类属性
3. 在本文件中 import
"""

from .account import DeviceAccountSaver
from .base import BaseSaver, as_list
from .firewall import AddressBookSaver, NatRuleSaver, PolicySaver, ServiceSaver
from .interface import InterfaceSaver
from .lb import (
    GtmDatacenterSaver,
    GtmPoolSaver,
    GtmServerSaver,
    GTMWideipSaver,
    LBPoolSaver,
    LBSnatSaver,
    LBVirtualServerSaver,
)
from .network import SnmpConfigSaver, VlanSaver
from .registry import get_savers_for_config
from .routing import RouteSaver, VrfSaver

__all__ = [
    "BaseSaver",
    "as_list",
    "DeviceAccountSaver",
    "InterfaceSaver",
    "AddressBookSaver",
    "ServiceSaver",
    "PolicySaver",
    "NatRuleSaver",
    "LBVirtualServerSaver",
    "LBPoolSaver",
    "LBSnatSaver",
    "GTMWideipSaver",
    "GtmDatacenterSaver",
    "GtmServerSaver",
    "GtmPoolSaver",
    "VlanSaver",
    "SnmpConfigSaver",
    "RouteSaver",
    "VrfSaver",
    "get_savers_for_config",
]
