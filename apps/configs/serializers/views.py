"""配置行序列化器（从 assets/serializers/views.py 迁入）。

继承 assets/serializers/base.py 的统一装饰器与基类——configs → assets 是合法依赖；
本模块只服务 configs 的模型，savers 与 MCP 工具都直接用这里的类。
"""

from rest_framework import serializers

from assets.serializers.base import DeviceRelatedSerializer, ParentClass, model
from assets.serializers.views import _format_address_entry, _format_service_entry
from configs import models as cm


@model(model=cm.DeviceConfig)
class DeviceConfigSerializer(ParentClass):
    device_name = serializers.CharField(source="device.hostname", read_only=True)


@model(model=cm.Vlan)
class VlanSerializer(DeviceRelatedSerializer):
    pass


@model(model=cm.Vrf)
class VrfSerializer(DeviceRelatedSerializer):
    pass


@model(model=cm.Interface)
class InterfaceSerializer(DeviceRelatedSerializer):
    vrf_name = serializers.CharField(source="vrf.name", read_only=True, default="")


@model(model=cm.DeviceAccount)
class DeviceAccountSerializer(DeviceRelatedSerializer):
    pass


@model(model=cm.SnmpConfig)
class SnmpConfigSerializer(DeviceRelatedSerializer):
    pass


@model(model=cm.NtpConfig)
class NtpConfigSerializer(DeviceRelatedSerializer):
    pass


@model(model=cm.SyslogConfig)
class SyslogConfigSerializer(DeviceRelatedSerializer):
    pass


@model(model=cm.LtmVirtualServer)
class LtmVirtualServerSerializer(DeviceRelatedSerializer):
    pass


@model(model=cm.LtmPool)
class LtmPoolSerializer(DeviceRelatedSerializer):
    pass


@model(model=cm.LtmPoolMember)
class LtmPoolMemberSerializer(DeviceRelatedSerializer):
    pass


@model(model=cm.LtmProfile)
class LtmProfileSerializer(DeviceRelatedSerializer):
    pass


@model(model=cm.LtmIRule)
class LtmIRuleSerializer(DeviceRelatedSerializer):
    pass


@model(model=cm.LtmSNAT)
class LtmSNATSerializer(DeviceRelatedSerializer):
    pass


@model(model=cm.LtmPersist)
class LtmPersistSerializer(DeviceRelatedSerializer):
    pass


@model(model=cm.GtmDatacenter)
class GtmDatacenterSerializer(DeviceRelatedSerializer):
    pass


@model(model=cm.GtmWideip)
class GtmWideipSerializer(DeviceRelatedSerializer):
    pass


@model(model=cm.GtmPool)
class GtmPoolSerializer(DeviceRelatedSerializer):
    pass


@model(model=cm.AddressBook)
class AddressBookSerializer(DeviceRelatedSerializer):
    parent_name = serializers.CharField(source="parent.name", read_only=True, default="")


@model(model=cm.GtmServer)
class GtmServerSerializer(DeviceRelatedSerializer):
    pass


@model(model=cm.GtmVServer)
class GtmVServerSerializer(DeviceRelatedSerializer):
    server_name = serializers.CharField(source="server.name", read_only=True, default="")


@model(model=cm.Service)
class ServiceSerializer(DeviceRelatedSerializer):
    pass


@model(model=cm.Policy)
class PolicySerializer(DeviceRelatedSerializer):
    # 跨表展示字段：源/目的地址来自 AddressBook、端口来自 Service（三个 M2M），
    # 直接给格式化好的字符串，前端表格列不必再逐条展开（配合视图侧 prefetch_related）
    source_addresses_display = serializers.SerializerMethodField()
    destination_addresses_display = serializers.SerializerMethodField()
    services_display = serializers.SerializerMethodField()

    def get_source_addresses_display(self, obj) -> list[str]:
        return [_format_address_entry(entry) for entry in obj.source_addresses.all()]

    def get_destination_addresses_display(self, obj) -> list[str]:
        return [_format_address_entry(entry) for entry in obj.destination_addresses.all()]

    def get_services_display(self, obj) -> list[str]:
        return [_format_service_entry(entry) for entry in obj.services.all()]


@model(model=cm.NatRule)
class NatRuleSerializer(DeviceRelatedSerializer):
    pass


@model(model=cm.Route)
class RouteSerializer(ParentClass):
    device_hostname = serializers.CharField(source="vrf.device.hostname", read_only=True, default="")

    vrf_name = serializers.CharField(source="vrf.name", read_only=True, default="")


@model(model=cm.ArpMac)
class ArpMacSerializer(DeviceRelatedSerializer):
    pass
