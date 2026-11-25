"""配置域 ViewSet（从 assets/api/views.py 迁入）。

URL 前缀 ``/api/configs/``（与 app 同名）：`DeviceConfigViewSet` 的堆叠组归属解析
随 `resolve_config_owner` 归本域。
"""

from rest_framework import viewsets

from assets.models import Device
from configs.config_owner import resolve_config_owner
from configs.models import (
    AddressBook,
    ArpMac,
    DeviceAccount,
    DeviceConfig,
    GtmDatacenter,
    GtmPool,
    GtmServer,
    GtmVServer,
    GtmWideip,
    Interface,
    LtmIRule,
    LtmPersist,
    LtmPool,
    LtmPoolMember,
    LtmProfile,
    LtmSNAT,
    LtmVirtualServer,
    NatRule,
    NtpConfig,
    Policy,
    Route,
    Service,
    SnmpConfig,
    SyslogConfig,
    Vlan,
    Vrf,
)
from configs.serializers.config import (
    AddressBookSerializer,
    ArpMacSerializer,
    DeviceAccountSerializer,
    DeviceConfigSerializer,
    GtmDatacenterSerializer,
    GtmPoolSerializer,
    GtmServerSerializer,
    GtmVServerSerializer,
    GtmWideipSerializer,
    InterfaceSerializer,
    LtmIRuleSerializer,
    LtmPersistSerializer,
    LtmPoolMemberSerializer,
    LtmPoolSerializer,
    LtmProfileSerializer,
    LtmSNATSerializer,
    LtmVirtualServerSerializer,
    NatRuleSerializer,
    NtpConfigSerializer,
    PolicySerializer,
    RouteSerializer,
    ServiceSerializer,
    SnmpConfigSerializer,
    SyslogConfigSerializer,
    VlanSerializer,
    VrfSerializer,
)


class DeviceConfigViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DeviceConfig.objects.select_related("device").all()
    serializer_class = DeviceConfigSerializer
    ordering_fields = ("collected_at",)

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            # 堆叠组备机没有自己的配置记录，查询统一回退到组内主设备
            device = Device.objects.filter(pk=device_id).first()
            if device:
                qs = qs.filter(device_id=resolve_config_owner(device).pk)
            else:
                qs = qs.filter(device_id=device_id)
        return qs


class VlanViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Vlan.objects.select_related("device").all()
    serializer_class = VlanSerializer
    search_fields = ("name", "vid", "description", "device__hostname")
    ordering_fields = ("vid", "name")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class VrfViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Vrf.objects.select_related("device").all()
    serializer_class = VrfSerializer
    search_fields = ("name", "device__hostname")
    ordering_fields = ("name", "created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class InterfaceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Interface.objects.select_related("device", "vrf").all()
    serializer_class = InterfaceSerializer
    search_fields = ("interface", "device__hostname", "ip_address")
    ordering_fields = ("interface", "created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        mode = self.request.query_params.get("mode")
        if mode:
            qs = qs.filter(mode=mode)
        return qs


class DeviceAccountViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DeviceAccount.objects.select_related("device").all()
    serializer_class = DeviceAccountSerializer
    search_fields = ("username", "description", "device__hostname")
    ordering_fields = ("username", "created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class SnmpConfigViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SnmpConfig.objects.select_related("device").all()
    serializer_class = SnmpConfigSerializer
    ordering_fields = ("created_at",)


class NtpConfigViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = NtpConfig.objects.select_related("device").all()
    serializer_class = NtpConfigSerializer
    ordering_fields = ("created_at",)


class SyslogConfigViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SyslogConfig.objects.select_related("device").all()
    serializer_class = SyslogConfigSerializer
    ordering_fields = ("created_at",)


class LtmVirtualServerViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = LtmVirtualServer.objects.select_related("device").all()
    serializer_class = LtmVirtualServerSerializer
    search_fields = ("name", "vs_address", "vs_port", "pool", "device__hostname")
    ordering_fields = ("name", "device__hostname", "created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class LtmPoolViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = LtmPool.objects.select_related("device").all()
    serializer_class = LtmPoolSerializer
    search_fields = ("name", "mode", "device__hostname")
    ordering_fields = ("name", "device__hostname", "created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class LtmPoolMemberViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = LtmPoolMember.objects.select_related("device").all()
    serializer_class = LtmPoolMemberSerializer
    search_fields = ("name", "address", "pool_name", "device__hostname")
    ordering_fields = ("name", "pool_name", "created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class LtmProfileViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = LtmProfile.objects.select_related("device").all()
    serializer_class = LtmProfileSerializer
    search_fields = ("name", "device__hostname")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class LtmIRuleViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = LtmIRule.objects.select_related("device").all()
    serializer_class = LtmIRuleSerializer
    search_fields = ("name", "device__hostname")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class LtmSNATViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = LtmSNAT.objects.select_related("device").all()
    serializer_class = LtmSNATSerializer
    search_fields = ("name", "device__hostname")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class LtmPersistViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = LtmPersist.objects.select_related("device").all()
    serializer_class = LtmPersistSerializer
    search_fields = ("name", "device__hostname")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class GtmDatacenterViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = GtmDatacenter.objects.select_related("device").all()
    serializer_class = GtmDatacenterSerializer
    search_fields = ("name", "device__hostname")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class GtmWideipViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = GtmWideip.objects.select_related("device").all()
    serializer_class = GtmWideipSerializer
    search_fields = ("name", "rtype", "lb_mode", "device__hostname")
    ordering_fields = ("name", "device__hostname", "created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class GtmPoolViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = GtmPool.objects.select_related("device").all()
    serializer_class = GtmPoolSerializer
    search_fields = ("name", "lb_mode", "fallback_ip", "device__hostname")
    ordering_fields = ("name", "device__hostname", "created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class GtmServerViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = GtmServer.objects.select_related("device").all()
    serializer_class = GtmServerSerializer
    search_fields = ("name", "datacenter", "device__hostname")
    ordering_fields = ("name", "created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class GtmVServerViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = GtmVServer.objects.select_related("device", "server").all()
    serializer_class = GtmVServerSerializer
    search_fields = ("name", "ip_address", "server__name", "device__hostname")
    ordering_fields = ("name", "port", "created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        server_id = self.request.query_params.get("server")
        if server_id:
            qs = qs.filter(server_id=server_id)
        return qs


class AddressBookViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AddressBook.objects.select_related("device", "parent").all()
    serializer_class = AddressBookSerializer
    search_fields = ("name", "device__hostname")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class ServiceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Service.objects.select_related("device").all()
    serializer_class = ServiceSerializer
    search_fields = ("name", "protocol")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class PolicyViewSet(viewsets.ReadOnlyModelViewSet):
    # 列表要展示源/目的地址（AddressBook）与端口（Service），三个 M2M 用 prefetch
    # 一次取回，避免逐行查询（N+1）
    queryset = Policy.objects.select_related("device").prefetch_related("source_addresses", "destination_addresses", "services").all()
    serializer_class = PolicySerializer
    search_fields = (
        "name",
        "policy_id",
        "device__hostname",
        "source_addresses__name",
        "destination_addresses__name",
        "services__name",
    )
    ordering_fields = ("order", "created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class NatRuleViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = NatRule.objects.select_related("device").all()
    serializer_class = NatRuleSerializer
    search_fields = ("name", "source_addresses__name", "destination_addresses__name", "device__hostname")
    ordering_fields = ("order", "created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class RouteViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Route.objects.select_related("vrf", "vrf__device").all()
    serializer_class = RouteSerializer
    search_fields = ("destination", "nexthop", "vrf__name", "vrf__device__hostname")
    ordering_fields = ("destination", "protocol", "metric")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(vrf__device_id=device_id)
        protocol = self.request.query_params.get("protocol")
        if protocol:
            qs = qs.filter(protocol=protocol)
        return qs


class ArpMacViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ArpMac.objects.select_related("device").all()
    serializer_class = ArpMacSerializer
    search_fields = ("ip_address", "mac_address", "device__hostname", "interface", "vendor")
    ordering_fields = ("ip_address", "mac_address", "vlan", "learned_at", "updated_at")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        vlan = self.request.query_params.get("vlan")
        if vlan:
            qs = qs.filter(vlan=vlan)
        arp_type = self.request.query_params.get("arp_type")
        if arp_type:
            qs = qs.filter(arp_type=arp_type)
        return qs
