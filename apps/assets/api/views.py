from rest_framework import viewsets

from assets.models import Cabinet, DataCenter, Device, DeviceConnection, DeviceModel, Room, SecurityZone, Vendor

from ..serializers.asset import (
    CabinetSerializer,
    DataCenterSerializer,
    DeviceConnectionSerializer,
    DeviceModelSerializer,
    DeviceSerializer,
    RoomSerializer,
    SecurityZoneSerializer,
    VendorSerializer,
)


class SecurityZoneViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SecurityZone.objects.all()
    serializer_class = SecurityZoneSerializer
    search_fields = ("name",)
    ordering_fields = ("name", "created_at")


class DataCenterViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DataCenter.objects.all()
    serializer_class = DataCenterSerializer
    search_fields = ("name", "address")
    ordering_fields = ("name", "created_at")


class RoomViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Room.objects.select_related("datacenter").all()
    serializer_class = RoomSerializer
    search_fields = ("name", "datacenter__name")
    ordering_fields = ("name", "created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        datacenter = self.request.query_params.get("datacenter")
        if datacenter:
            qs = qs.filter(datacenter_id=datacenter)
        return qs


class CabinetViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Cabinet.objects.select_related("room", "room__datacenter").all()
    serializer_class = CabinetSerializer
    search_fields = ("name", "room__name", "room__datacenter__name")
    ordering_fields = ("name", "status", "created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        room = self.request.query_params.get("room")
        if room:
            qs = qs.filter(room_id=room)
        datacenter = self.request.query_params.get("datacenter")
        if datacenter:
            qs = qs.filter(room__datacenter_id=datacenter)
        status = self.request.query_params.get("status")
        if status:
            qs = qs.filter(status=status)
        return qs


class VendorViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Vendor.objects.all()
    serializer_class = VendorSerializer
    search_fields = ("name",)
    ordering_fields = ("name",)


class DeviceModelViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DeviceModel.objects.select_related("vendor").all()
    serializer_class = DeviceModelSerializer
    search_fields = ("name", "vendor__name")
    ordering_fields = ("name",)


class DeviceGroupViewSet(viewsets.ReadOnlyModelViewSet):
    from assets.models import DeviceGroup

    from ..serializers.asset import DeviceGroupSerializer

    queryset = DeviceGroup.objects.prefetch_related("members").all()
    serializer_class = DeviceGroupSerializer
    search_fields = ("name", "description")
    ordering_fields = ("name", "created_at")


class DeviceGroupMemberViewSet(viewsets.ReadOnlyModelViewSet):
    from assets.models import DeviceGroupMember

    from ..serializers.asset import DeviceGroupMemberSerializer

    queryset = DeviceGroupMember.objects.select_related("group", "device").all()
    serializer_class = DeviceGroupMemberSerializer
    search_fields = ("device__hostname", "group__name")
    ordering_fields = ("created_at",)

    def get_queryset(self):
        qs = super().get_queryset()
        group_id = self.request.query_params.get("group")
        if group_id:
            qs = qs.filter(group_id=group_id)
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class DeviceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Device.objects.select_related("idc", "cabinet", "security_zone", "device_model").all()
    serializer_class = DeviceSerializer
    search_fields = ("hostname", "ip_address")
    ordering_fields = ("hostname", "created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        device_type = self.request.query_params.get("device_type")
        if device_type:
            qs = qs.filter(device_type=device_type)
        idc = self.request.query_params.get("idc")
        if idc:
            qs = qs.filter(idc_id=idc)
        return qs


class DeviceConnectionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DeviceConnection.objects.select_related("device").all()
    serializer_class = DeviceConnectionSerializer
    search_fields = ("username", "device__hostname")
    ordering_fields = ("created_at",)

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class TagViewSet(viewsets.ReadOnlyModelViewSet):
    from assets.models import Tag

    from ..serializers.asset import TagSerializer

    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    search_fields = ("name",)
    ordering_fields = ("name", "created_at")


class SubnetViewSet(viewsets.ReadOnlyModelViewSet):
    from assets.models import Subnet

    from ..serializers.asset import SubnetSerializer

    queryset = Subnet.objects.prefetch_related("tags").all()
    serializer_class = SubnetSerializer
    search_fields = ("network", "description")
    ordering_fields = ("network", "created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        datacenter = self.request.query_params.get("datacenter")
        if datacenter:
            qs = qs.filter(datacenter_id=datacenter)
        tag = self.request.query_params.get("tag")
        if tag:
            qs = qs.filter(tags__id=tag)
        return qs


class IPAddressViewSet(viewsets.ReadOnlyModelViewSet):
    from assets.models import IPAddress

    from ..serializers.asset import IPAddressSerializer

    queryset = IPAddress.objects.select_related("subnet", "device", "security_zone").all()
    serializer_class = IPAddressSerializer
    search_fields = ("ip_address", "description", "device__hostname")
    ordering_fields = ("ip_address", "created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        subnet = self.request.query_params.get("subnet")
        if subnet:
            qs = qs.filter(subnet_id=subnet)
        status = self.request.query_params.get("status")
        if status:
            qs = qs.filter(status=status)
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class TopologyViewSet(viewsets.ReadOnlyModelViewSet):
    from assets.models import Topology

    from ..serializers.asset import TopologySerializer

    queryset = Topology.objects.all()
    serializer_class = TopologySerializer
    search_fields = ("name", "description")
    ordering_fields = ("name", "updated_at")


class SubnetUsageLogViewSet(viewsets.ReadOnlyModelViewSet):
    from assets.models import SubnetUsageLog

    from ..serializers.asset import SubnetUsageLogSerializer

    queryset = SubnetUsageLog.objects.select_related("subnet").all()
    serializer_class = SubnetUsageLogSerializer
    ordering_fields = ("recorded_at", "utilization")

    def get_queryset(self):
        qs = super().get_queryset()
        subnet_id = self.request.query_params.get("subnet")
        if subnet_id:
            qs = qs.filter(subnet_id=subnet_id)
        return qs


# 统一配置项体系（T1）：序列化器口径见 assets/serializers/asset.py
class ConfigurationItemViewSet(viewsets.ReadOnlyModelViewSet):
    from assets.models import ConfigurationItem
    from assets.serializers.asset import ConfigurationItemSerializer

    queryset = ConfigurationItem.objects.all()
    serializer_class = ConfigurationItemSerializer
    search_fields = ("ci_id", "name", "description")
    ordering_fields = ("ci_type", "name", "created_at", "updated_at")

    def get_queryset(self):
        qs = super().get_queryset()
        ci_type = self.request.query_params.get("ci_type")
        if ci_type:
            qs = qs.filter(ci_type=ci_type)
        return qs


class PhysicalServerViewSet(viewsets.ReadOnlyModelViewSet):
    from assets.models import PhysicalServer
    from assets.serializers.asset import PhysicalServerSerializer

    queryset = PhysicalServer.objects.select_related("ci").all()
    serializer_class = PhysicalServerSerializer
    search_fields = ("hostname", "serial_number", "ci__name", "ci__ci_id")
    ordering_fields = ("hostname", "created_at")


class VirtualMachineViewSet(viewsets.ReadOnlyModelViewSet):
    from assets.models import VirtualMachine
    from assets.serializers.asset import VirtualMachineSerializer

    queryset = VirtualMachine.objects.select_related("ci").all()
    serializer_class = VirtualMachineSerializer
    search_fields = ("hostname", "host_name", "ci__name", "ci__ci_id")
    ordering_fields = ("hostname", "created_at")


class DatabaseInstanceViewSet(viewsets.ReadOnlyModelViewSet):
    from assets.models import DatabaseInstance
    from assets.serializers.asset import DatabaseInstanceSerializer

    queryset = DatabaseInstance.objects.select_related("ci").all()
    serializer_class = DatabaseInstanceSerializer
    search_fields = ("engine", "version", "host_name", "ci__name", "ci__ci_id")
    ordering_fields = ("engine", "created_at")


class ApplicationServiceViewSet(viewsets.ReadOnlyModelViewSet):
    from assets.models import ApplicationService
    from assets.serializers.asset import ApplicationServiceSerializer

    queryset = ApplicationService.objects.select_related("ci").all()
    serializer_class = ApplicationServiceSerializer
    search_fields = ("service_type", "url_path", "ci__name", "ci__ci_id")
    ordering_fields = ("service_type", "created_at")


# 统一关系表（T3）：支持 ?ci_id= 命中任一端
class CIRelationshipViewSet(viewsets.ReadOnlyModelViewSet):
    from assets.models import CIRelationship
    from assets.serializers.asset import CIRelationshipSerializer

    queryset = CIRelationship.objects.all()
    serializer_class = CIRelationshipSerializer
    search_fields = ("src_ci_id", "dst_ci_id")
    ordering_fields = ("src_ci_id", "dst_ci_id", "relation_type", "created_at")

    def get_queryset(self):
        from django.db.models import Q

        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("src_ci_id"):
            qs = qs.filter(src_ci_id=params["src_ci_id"])
        if params.get("dst_ci_id"):
            qs = qs.filter(dst_ci_id=params["dst_ci_id"])
        if params.get("ci_id"):
            qs = qs.filter(Q(src_ci_id=params["ci_id"]) | Q(dst_ci_id=params["ci_id"]))
        if params.get("relation_type"):
            qs = qs.filter(relation_type=params["relation_type"])
        return qs


# 软资产归并（T4）：只读，写入只由 sync_soft_assets 负责
class DomainAssetViewSet(viewsets.ReadOnlyModelViewSet):
    from assets.models import DomainAsset
    from assets.serializers.asset import DomainAssetSerializer

    queryset = DomainAsset.objects.select_related("ci").all()
    serializer_class = DomainAssetSerializer
    # JSON 字段不能进 search_fields（PG 的 jsonb 不支持 icontains），按设备 / VIP 走精确过滤
    search_fields = ("fqdn", "ci__ci_id", "ci__name")
    ordering_fields = ("fqdn", "ttl", "created_at", "updated_at")

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("inconsistent") in ("true", "false"):
            qs = qs.filter(inconsistent=params["inconsistent"] == "true")
        if params.get("device"):
            qs = qs.filter(devices__contains=[params["device"]])
        if params.get("vip"):
            qs = qs.filter(vips__contains=[params["vip"]])
        return qs


class LoadBalancerServiceViewSet(viewsets.ReadOnlyModelViewSet):
    from assets.models import LoadBalancerService
    from assets.serializers.asset import LoadBalancerServiceSerializer

    queryset = LoadBalancerService.objects.select_related("ci").all()
    serializer_class = LoadBalancerServiceSerializer
    search_fields = ("asset_key", "vip", "port", "ci__ci_id", "ci__name")
    ordering_fields = ("vip", "port", "member_count", "created_at", "updated_at")

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("inconsistent") in ("true", "false"):
            qs = qs.filter(inconsistent=params["inconsistent"] == "true")
        if params.get("device"):
            qs = qs.filter(devices__contains=[params["device"]])
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("port"):
            qs = qs.filter(port=params["port"])
        return qs
