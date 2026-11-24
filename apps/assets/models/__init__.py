"""资产域模型包：本文件**只做 re-export**，模型定义在子模块（见 handbook/assets.md）。

不能同时留 ``models.py`` 与 ``models/``：包优先，单文件会被静默忽略。
"""

from .ci import (
    CI_TYPE_CHOICES,
    PHYSICAL_TYPES,
    SOFT_TYPES,
    ApplicationService,
    CIType,
    ConfigurationItem,
    DatabaseInstance,
    PhysicalServer,
    VirtualMachine,
    _CIExtension,
)
from .network import (
    Cabinet,
    DataCenter,
    Device,
    DeviceConnection,
    DeviceGroup,
    DeviceGroupMember,
    DeviceModel,
    IPAddress,
    Room,
    SecurityZone,
    ServerOwner,
    Subnet,
    SubnetUsageLog,
    Tag,
    Topology,
    Vendor,
)
from .registry import CI_OBJECT_CHOICES, CIObjectLink, CIObjectType
from .relations import (
    CI_RELATION_CHOICES,
    CIRelationship,
    CIRelationType,
)
from .soft_assets import (
    DomainAsset,
    LoadBalancerService,
)

__all__ = [
    "CI_TYPE_CHOICES",
    "PHYSICAL_TYPES",
    "SOFT_TYPES",
    "ApplicationService",
    "CIType",
    "ConfigurationItem",
    "DatabaseInstance",
    "PhysicalServer",
    "VirtualMachine",
    "_CIExtension",
    "Cabinet",
    "DataCenter",
    "Device",
    "DeviceConnection",
    "DeviceGroup",
    "DeviceGroupMember",
    "DeviceModel",
    "IPAddress",
    "Room",
    "SecurityZone",
    "ServerOwner",
    "Subnet",
    "SubnetUsageLog",
    "Tag",
    "Topology",
    "Vendor",
    "CI_RELATION_CHOICES",
    "CIRelationType",
    "CIRelationship",
    "CIObjectLink",
    "CIObjectType",
    "CI_OBJECT_CHOICES",
    "DomainAsset",
    "LoadBalancerService",
]
