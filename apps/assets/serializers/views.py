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

    group_type_display = serializers.SerializerMethodField()

    def get_member_count(self, obj) -> int:
        # 配合 viewset 的 prefetch_related("members")，这里不会额外查库
        return len(obj.members.all())

    def get_group_type_display(self, obj) -> str:
        """组类型的中文名。

        MCP 工具只按序列化器口径取字段（不在工具层调 ``get_FOO_display``），
        缺这个键，`list_records` / `get_record` 里就只剩 ``ha`` 这种内部值。
        """
        return obj.get_group_type_display() or ""


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
class LtmPoolMemberSerializer(DeviceRelatedSerializer):
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


@model(model=models.ServerOwner)
class ServerOwnerSerializer(ParentClass):
    pass


# 统一配置项体系（T1）：现阶段只做信息录入与查询，不做生命周期管理


@model(model=models.ConfigurationItem)
class ConfigurationItemSerializer(ParentClass):
    ci_type_display = serializers.CharField(source="get_ci_type_display", read_only=True)

    class Meta:
        model = models.ConfigurationItem
        fields = (
            "id",
            "ci_id",
            "ci_type",
            "ci_type_display",
            "name",
            "description",
            "tags",
            "monitor_status",
            "created_at",
            "updated_at",
        )
        # ci_id 由服务端生成且不可变；monitor_status 是 T15 状态回写的预留字段，不开放录入
        read_only_fields = ("id", "ci_id", "monitor_status", "created_at", "updated_at")


class CIExtensionSerializerMixin:
    """扩展模型录入校验：所属 CI 的 ci_type 必须匹配。

    不在这里挡住，就会落到模型 ``save()`` 抛 ValueError，DRF 不认识它、直接变 500。
    """

    EXPECTED_CI_TYPE = ""

    def validate(self, attrs: dict) -> dict:
        ci = attrs.get("ci")
        if ci is not None and ci.ci_type != self.EXPECTED_CI_TYPE:
            raise serializers.ValidationError({"ci": f"配置项类型须为 {self.EXPECTED_CI_TYPE}，当前为 {ci.ci_type}"})
        return attrs


@model(model=models.PhysicalServer)
class PhysicalServerSerializer(CIExtensionSerializerMixin, ParentClass):
    EXPECTED_CI_TYPE = models.CIType.PHYSICAL_SERVER


@model(model=models.VirtualMachine)
class VirtualMachineSerializer(CIExtensionSerializerMixin, ParentClass):
    EXPECTED_CI_TYPE = models.CIType.VIRTUAL_MACHINE


@model(model=models.DatabaseInstance)
class DatabaseInstanceSerializer(CIExtensionSerializerMixin, ParentClass):
    EXPECTED_CI_TYPE = models.CIType.DATABASE_INSTANCE


@model(model=models.ApplicationService)
class ApplicationServiceSerializer(CIExtensionSerializerMixin, ParentClass):
    EXPECTED_CI_TYPE = models.CIType.APPLICATION_SERVICE


# 统一关系表（T3）：只登记直接关系，两端 ci_id 的存在性与自环在录入时校验


@model(model=models.CIRelationship)
class CIRelationshipSerializer(ParentClass):
    relation_type_display = serializers.CharField(source="get_relation_type_display", read_only=True)

    class Meta:
        model = models.CIRelationship
        fields = ("id", "src_ci_id", "dst_ci_id", "relation_type", "relation_type_display", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs: dict) -> dict:
        src = attrs.get("src_ci_id", getattr(self.instance, "src_ci_id", None))
        dst = attrs.get("dst_ci_id", getattr(self.instance, "dst_ci_id", None))
        if src and dst and src == dst:
            raise serializers.ValidationError({"dst_ci_id": "关系两端不能是同一个 CI"})
        wanted = {value for value in (src, dst) if value}
        known = set(models.ConfigurationItem.objects.filter(ci_id__in=wanted).values_list("ci_id", flat=True))
        for field, value in (("src_ci_id", src), ("dst_ci_id", dst)):
            if value and value not in known:
                raise serializers.ValidationError({field: f"CI 标识 {value} 不存在"})
        return attrs
