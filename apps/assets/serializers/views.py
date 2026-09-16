"""资产序列化器（API 视图与解析入库共用）。

从 apps/assets/api/serializers.py 迁移而来，改造点：

- 通用展示字段 ``device_hostname`` 上提到 ``DeviceRelatedSerializer``
- ``Meta`` 由 ``@model`` 装饰器统一注入（``fields="__all__"``、仅主键只读）
- 各序列化器只保留自己特有的展示字段与方法

需要精简字段的场景（例如列表页不想带大 JSON），在类体内自定义 ``Meta`` 即可，
装饰器会尊重子类的定义。
"""

from rest_framework import serializers

from assets import models

from .base import DeviceRelatedSerializer, ParentClass, model


@model(model=models.SecurityZone)
class SecurityZoneSerializer(ParentClass):
    pass


@model(model=models.DataCenter)
class DataCenterSerializer(ParentClass):
    room_count = serializers.IntegerField(source="rooms.count", read_only=True)

    cabinet_count = serializers.SerializerMethodField()

    def get_cabinet_count(self, obj) -> int:
        return models.Cabinet.objects.filter(room__datacenter=obj).count()


@model(model=models.Room)
class RoomSerializer(ParentClass):
    datacenter_name = serializers.CharField(source="datacenter.name", read_only=True)

    cabinet_count = serializers.IntegerField(source="cabinets.count", read_only=True)


@model(model=models.Cabinet)
class CabinetSerializer(ParentClass):
    room_name = serializers.CharField(source="room.name", read_only=True)

    datacenter_name = serializers.CharField(source="room.datacenter.name", read_only=True)


@model(model=models.Vendor)
class VendorSerializer(ParentClass):
    model_count = serializers.IntegerField(source="device_models.count", read_only=True)


@model(model=models.DeviceModel)
class DeviceModelSerializer(ParentClass):
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)


@model(model=models.DeviceGroup)
class DeviceGroupSerializer(ParentClass):
    member_count = serializers.SerializerMethodField()

    def get_member_count(self, obj) -> int:
        # 配合 viewset 的 prefetch_related("members")，这里不会额外查库
        return len(obj.members.all())


@model(model=models.DeviceGroupMember)
class DeviceGroupMemberSerializer(DeviceRelatedSerializer):
    group_name = serializers.CharField(source="group.name", read_only=True, default="")

    group_type = serializers.CharField(source="group.group_type", read_only=True, default="")


@model(model=models.Device)
class DeviceSerializer(ParentClass):
    idc_name = serializers.CharField(source="idc.name", read_only=True, default="")

    cabinet_name = serializers.CharField(source="cabinet", read_only=True, default="")

    room_name = serializers.CharField(source="cabinet.room.name", read_only=True, default="")

    security_zone_name = serializers.CharField(source="security_zone", read_only=True, default="")

    device_model_name = serializers.CharField(source="device_model", read_only=True, default="")

    device_type_display = serializers.SerializerMethodField()

    def get_device_type_display(self, obj):
        return obj.get_device_type_display() or ""


@model(model=models.DeviceConfig)
class DeviceConfigSerializer(ParentClass):
    device_name = serializers.CharField(source="device.hostname", read_only=True)


@model(model=models.DeviceConnection)
class DeviceConnectionSerializer(ParentClass):
    device_name = serializers.CharField(source="device.hostname", read_only=True, default="")


@model(model=models.Vlan)
class VlanSerializer(DeviceRelatedSerializer):
    pass


@model(model=models.Vrf)
class VrfSerializer(DeviceRelatedSerializer):
    pass


@model(model=models.Interface)
class InterfaceSerializer(DeviceRelatedSerializer):
    vrf_name = serializers.CharField(source="vrf.name", read_only=True, default="")


@model(model=models.DeviceAccount)
class DeviceAccountSerializer(DeviceRelatedSerializer):
    pass


@model(model=models.SnmpConfig)
class SnmpConfigSerializer(DeviceRelatedSerializer):
    pass


@model(model=models.NtpConfig)
class NtpConfigSerializer(DeviceRelatedSerializer):
    pass


@model(model=models.SyslogConfig)
class SyslogConfigSerializer(DeviceRelatedSerializer):
    pass


@model(model=models.LtmVirtualServer)
class LtmVirtualServerSerializer(DeviceRelatedSerializer):
    pass


@model(model=models.LtmPool)
class LtmPoolSerializer(DeviceRelatedSerializer):
    pass


@model(model=models.LtmPoolMember)
class LtmPoolMemberSerializer(ParentClass):
    pass


@model(model=models.LtmProfile)
class LtmProfileSerializer(DeviceRelatedSerializer):
    pass


@model(model=models.LtmIRule)
class LtmIRuleSerializer(DeviceRelatedSerializer):
    pass


@model(model=models.LtmSNAT)
class LtmSNATSerializer(DeviceRelatedSerializer):
    pass


@model(model=models.LtmPersist)
class LtmPersistSerializer(DeviceRelatedSerializer):
    pass


@model(model=models.GtmDatacenter)
class GtmDatacenterSerializer(DeviceRelatedSerializer):
    pass


@model(model=models.GtmWideip)
class GtmWideipSerializer(DeviceRelatedSerializer):
    pass


@model(model=models.GtmPool)
class GtmPoolSerializer(DeviceRelatedSerializer):
    pass


@model(model=models.AddressBook)
class AddressBookSerializer(DeviceRelatedSerializer):
    parent_name = serializers.CharField(source="parent.name", read_only=True, default="")


@model(model=models.GtmServer)
class GtmServerSerializer(DeviceRelatedSerializer):
    pass


@model(model=models.GtmVServer)
class GtmVServerSerializer(DeviceRelatedSerializer):
    server_name = serializers.CharField(source="server.name", read_only=True, default="")


@model(model=models.Service)
class ServiceSerializer(DeviceRelatedSerializer):
    pass


@model(model=models.Policy)
class PolicySerializer(DeviceRelatedSerializer):
    pass


@model(model=models.NatRule)
class NatRuleSerializer(DeviceRelatedSerializer):
    pass


@model(model=models.Tag)
class TagSerializer(ParentClass):
    subnet_count = serializers.IntegerField(source="subnets.count", read_only=True)


@model(model=models.Subnet)
class SubnetSerializer(ParentClass):
    tag_names = serializers.SerializerMethodField()

    ip_count = serializers.IntegerField(source="ip_addresses.count", read_only=True)

    total_ips = serializers.IntegerField(read_only=True)

    used_ips = serializers.IntegerField(read_only=True)

    utilization = serializers.FloatField(read_only=True)

    def get_tag_names(self, obj):
        return list(obj.tags.values_list("name", flat=True))


@model(model=models.IPAddress)
class IPAddressSerializer(DeviceRelatedSerializer):
    subnet_network = serializers.CharField(source="subnet.network", read_only=True, default="")

    security_zone_name = serializers.CharField(source="security_zone.name", read_only=True, default="")


@model(model=models.Route)
class RouteSerializer(ParentClass):
    device_hostname = serializers.CharField(source="vrf.device.hostname", read_only=True, default="")

    vrf_name = serializers.CharField(source="vrf.name", read_only=True, default="")


@model(model=models.Topology)
class TopologySerializer(ParentClass):
    pass


@model(model=models.ArpMac)
class ArpMacSerializer(DeviceRelatedSerializer):
    pass


@model(model=models.SubnetUsageLog)
class SubnetUsageLogSerializer(ParentClass):
    subnet_network = serializers.CharField(source="subnet.network", read_only=True, default="")
