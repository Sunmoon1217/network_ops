import logging

from django.http import HttpResponse, JsonResponse
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from assets.device_import import IMPORT_SHEETS
from assets.models import (
    AddressBook,
    ArpMac,
    Cabinet,
    DataCenter,
    Device,
    DeviceAccount,
    DeviceConfig,
    DeviceConnection,
    DeviceModel,
    GtmDatacenter,
    GtmPool,
    GtmWideip,
    Interface,
    LtmPool,
    LtmPoolMember,
    LtmVirtualServer,
    NatRule,
    NtpConfig,
    Policy,
    Room,
    Route,
    SecurityZone,
    Service,
    SnmpConfig,
    Subnet,
    SyslogConfig,
    Vendor,
    Vlan,
    Vrf,
)

from .serializers import (
    CabinetSerializer,
    DataCenterSerializer,
    DeviceAccountSerializer,
    DeviceConfigSerializer,
    DeviceConnectionSerializer,
    DeviceModelSerializer,
    DeviceSerializer,
    InterfaceSerializer,
    NtpConfigSerializer,
    RoomSerializer,
    SecurityZoneSerializer,
    SnmpConfigSerializer,
    SyslogConfigSerializer,
    VendorSerializer,
    VlanSerializer,
    VrfSerializer,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


def overview(request):
    """资产管理概览统计"""
    from django.db.models import Count

    # --- 基础设施 ---
    cabinets_by_dc = list(
        Cabinet.objects.values("room__datacenter__name").annotate(count=Count("id")).order_by("-count")[:10]
    )
    cabinets_by_status = list(Cabinet.objects.values("status").annotate(count=Count("id")))

    # --- 设备 ---
    device_types = list(Device.objects.values("device_type").annotate(count=Count("id")).order_by("-count"))
    devices_by_vendor = list(
        Device.objects.values("device_model__vendor__name").annotate(count=Count("id")).order_by("-count")[:10]
    )
    devices_by_zone = list(Device.objects.values("security_zone__name").annotate(count=Count("id")).order_by("-count"))

    # --- 接口 ---
    interface_modes = list(Interface.objects.values("mode").annotate(count=Count("id")))

    # --- 路由 ---
    route_protocols = list(Route.objects.values("protocol").annotate(count=Count("id")).order_by("-count"))
    routes_by_device = list(
        Route.objects.values("vrf__device__hostname").annotate(count=Count("id")).order_by("-count")[:10]
    )

    # --- 防火墙 ---
    policies_by_action = list(Policy.objects.values("action").annotate(count=Count("id")))
    nat_by_type = list(NatRule.objects.values("nat_type").annotate(count=Count("id")))
    address_books_by_type = list(AddressBook.objects.values("address_type").annotate(count=Count("id")))
    services_by_protocol = list(Service.objects.values("protocol").annotate(count=Count("id")))

    # --- IPAM ---
    subnets_by_dc = list(Subnet.objects.values("datacenter__name").annotate(count=Count("id")).order_by("-count"))
    subnets_by_zone = list(Subnet.objects.values("security_zone__name").annotate(count=Count("id")).order_by("-count"))

    # --- SLB ---
    vs_by_protocol = list(LtmVirtualServer.objects.values("protocol").annotate(count=Count("id")))
    pools_by_lb = list(LtmPool.objects.values("device__hostname").annotate(count=Count("id")).order_by("-count")[:10])

    return JsonResponse(
        {
            # 基础设施
            "dc_count": DataCenter.objects.count(),
            "room_count": Room.objects.count(),
            "cabinet_count": Cabinet.objects.count(),
            "cabinet_active": Cabinet.objects.filter(status="active").count(),
            "cabinets_by_dc": cabinets_by_dc,
            "cabinets_by_status": cabinets_by_status,
            "security_zone_count": SecurityZone.objects.count(),
            # 设备
            "device_count": Device.objects.count(),
            "device_types": device_types,
            "vendor_count": Vendor.objects.count(),
            "device_model_count": DeviceModel.objects.count(),
            "devices_by_vendor": devices_by_vendor,
            "devices_by_zone": devices_by_zone,
            # 接口
            "interface_count": Interface.objects.count(),
            "interface_up": Interface.objects.filter(enabled=True).count(),
            "interface_modes": interface_modes,
            # 网络
            "vlan_count": Vlan.objects.count(),
            "vrf_count": Vrf.objects.count(),
            "route_count": Route.objects.count(),
            "route_protocols": route_protocols,
            "routes_by_device": routes_by_device,
            # 负载均衡
            "vs_count": LtmVirtualServer.objects.count(),
            "pool_count": LtmPool.objects.count(),
            "pool_member_count": LtmPoolMember.objects.count(),
            "vs_by_protocol": vs_by_protocol,
            "pools_by_lb": pools_by_lb,
            # 全局负载均衡
            "gtm_dc_count": GtmDatacenter.objects.count(),
            "gtm_wideip_count": GtmWideip.objects.count(),
            "gtm_pool_count": GtmPool.objects.count(),
            # 防火墙
            "address_book_count": AddressBook.objects.count(),
            "service_count": Service.objects.count(),
            "policy_count": Policy.objects.count(),
            "nat_rule_count": NatRule.objects.count(),
            "policies_by_action": policies_by_action,
            "nat_by_type": nat_by_type,
            "address_books_by_type": address_books_by_type,
            "services_by_protocol": services_by_protocol,
            # IPAM
            "subnet_count": Subnet.objects.count(),
            "arp_mac_count": ArpMac.objects.count(),
            "subnets_by_dc": subnets_by_dc,
            "subnets_by_zone": subnets_by_zone,
        }
    )


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([AllowAny])
def import_excel(request):
    """导入 Excel 文件，支持多个 Sheet"""
    from openpyxl import load_workbook

    excel_file = request.FILES.get("file")
    if not excel_file:
        return Response({"error": "请上传 Excel 文件"}, status=400)

    try:
        wb = load_workbook(excel_file, read_only=True, data_only=True)
    except Exception as e:
        return Response({"error": f"文件格式错误: {e}"}, status=400)

    results = {}
    # Sheet 清单 / 列头 / 导入函数的唯一来源是模块级 IMPORT_SHEETS（定义在各 _import_* 之后，
    # 运行期才查名字，此处直接引用即可）——模板下载接口读同一份表，两者不可能漂移。

    for sheet_name, spec in IMPORT_SHEETS.items():
        if sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            try:
                results[sheet_name] = spec["importer"](ws)
            except Exception as e:
                logger.error("导入 %s 失败: %s", sheet_name, e)
                results[sheet_name] = {"created": 0, "updated": 0, "errors": [str(e)]}
        else:
            results[sheet_name] = {"created": 0, "updated": 0, "errors": [], "skipped": True}

    wb.close()
    return Response({"success": True, "results": results})


@api_view(["GET"])
@permission_classes([AllowAny])
def import_template(request):
    """下载导入模板（xlsx）：每个 Sheet 一行列头，列头取自 IMPORT_SHEETS。

    只写表头、**不放示例行**——示例行留在模板里，用户忘了删就会被当成数据导进来。
    """
    from io import BytesIO
    from urllib.parse import quote

    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    if ws:
        wb.remove(ws)
    for sheet_name, spec in IMPORT_SHEETS.items():
        ws = wb.create_sheet(title=sheet_name)
        ws.append(spec["headers"])
        # 中文按两个字符宽估，够看清表头即可
        for idx, header in enumerate(spec["headers"], start=1):
            ws.column_dimensions[get_column_letter(idx)].width = len(header) * 2 + 4

    buf = BytesIO()
    wb.save(buf)
    response = HttpResponse(
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote('设备导入模板.xlsx')}"
    return response


# ---------------------------------------------------------------------------
# DCIM ViewSets
# ---------------------------------------------------------------------------


class SecurityZoneViewSet(viewsets.ModelViewSet):
    queryset = SecurityZone.objects.all()
    serializer_class = SecurityZoneSerializer
    permission_classes = (AllowAny,)
    search_fields = ("name",)
    ordering_fields = ("name", "created_at")


class DataCenterViewSet(viewsets.ModelViewSet):
    queryset = DataCenter.objects.all()
    serializer_class = DataCenterSerializer
    permission_classes = (AllowAny,)
    search_fields = ("name", "address")
    ordering_fields = ("name", "created_at")


class RoomViewSet(viewsets.ModelViewSet):
    queryset = Room.objects.select_related("datacenter").all()
    serializer_class = RoomSerializer
    permission_classes = (AllowAny,)
    search_fields = ("name", "datacenter__name")
    ordering_fields = ("name", "created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        datacenter = self.request.query_params.get("datacenter")
        if datacenter:
            qs = qs.filter(datacenter_id=datacenter)
        return qs


class CabinetViewSet(viewsets.ModelViewSet):
    queryset = Cabinet.objects.select_related("room", "room__datacenter").all()
    serializer_class = CabinetSerializer
    permission_classes = (AllowAny,)
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


class VendorViewSet(viewsets.ModelViewSet):
    queryset = Vendor.objects.all()
    serializer_class = VendorSerializer
    permission_classes = (AllowAny,)
    search_fields = ("name",)
    ordering_fields = ("name",)


class DeviceModelViewSet(viewsets.ModelViewSet):
    queryset = DeviceModel.objects.select_related("vendor").all()
    serializer_class = DeviceModelSerializer
    permission_classes = (AllowAny,)
    search_fields = ("name", "vendor__name")
    ordering_fields = ("name",)


class DeviceGroupViewSet(viewsets.ModelViewSet):
    from assets.models import DeviceGroup

    from .serializers import DeviceGroupSerializer

    queryset = DeviceGroup.objects.prefetch_related("members").all()
    serializer_class = DeviceGroupSerializer
    permission_classes = (AllowAny,)
    search_fields = ("name", "description")
    ordering_fields = ("name", "created_at")


class DeviceGroupMemberViewSet(viewsets.ModelViewSet):
    from assets.models import DeviceGroupMember

    from .serializers import DeviceGroupMemberSerializer

    queryset = DeviceGroupMember.objects.select_related("group", "device").all()
    serializer_class = DeviceGroupMemberSerializer
    permission_classes = (AllowAny,)
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


class DeviceViewSet(viewsets.ModelViewSet):
    queryset = Device.objects.select_related("idc", "cabinet", "security_zone", "device_model").all()
    serializer_class = DeviceSerializer
    permission_classes = (AllowAny,)
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


class DeviceConfigViewSet(viewsets.ModelViewSet):
    queryset = DeviceConfig.objects.select_related("device").all()
    serializer_class = DeviceConfigSerializer
    permission_classes = (AllowAny,)
    ordering_fields = ("collected_at",)

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            # 堆叠组备机没有自己的配置记录，查询统一回退到组内主设备
            device = Device.objects.filter(pk=device_id).first()
            if device:
                from ingest.config_owner import resolve_config_owner

                qs = qs.filter(device_id=resolve_config_owner(device).pk)
            else:
                qs = qs.filter(device_id=device_id)
        return qs


class DeviceConnectionViewSet(viewsets.ModelViewSet):
    queryset = DeviceConnection.objects.select_related("device").all()
    serializer_class = DeviceConnectionSerializer
    permission_classes = (AllowAny,)
    search_fields = ("username", "device__hostname")
    ordering_fields = ("created_at",)

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


# ---------------------------------------------------------------------------
# Network ViewSets
# ---------------------------------------------------------------------------


class VlanViewSet(viewsets.ModelViewSet):
    queryset = Vlan.objects.select_related("device").all()
    serializer_class = VlanSerializer
    permission_classes = (AllowAny,)
    search_fields = ("name", "vid", "description", "device__hostname")
    ordering_fields = ("vid", "name")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class VrfViewSet(viewsets.ModelViewSet):
    queryset = Vrf.objects.select_related("device").all()
    serializer_class = VrfSerializer
    permission_classes = (AllowAny,)
    search_fields = ("name", "device__hostname")
    ordering_fields = ("name", "created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class InterfaceViewSet(viewsets.ModelViewSet):
    queryset = Interface.objects.select_related("device", "vrf").all()
    serializer_class = InterfaceSerializer
    permission_classes = (AllowAny,)
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


class DeviceAccountViewSet(viewsets.ModelViewSet):
    queryset = DeviceAccount.objects.select_related("device").all()
    serializer_class = DeviceAccountSerializer
    permission_classes = (AllowAny,)
    search_fields = ("username", "description", "device__hostname")
    ordering_fields = ("username", "created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


# ---------------------------------------------------------------------------
# Baseline ViewSets
# ---------------------------------------------------------------------------


class SnmpConfigViewSet(viewsets.ModelViewSet):
    queryset = SnmpConfig.objects.select_related("device").all()
    serializer_class = SnmpConfigSerializer
    permission_classes = (AllowAny,)
    ordering_fields = ("created_at",)


class NtpConfigViewSet(viewsets.ModelViewSet):
    queryset = NtpConfig.objects.select_related("device").all()
    serializer_class = NtpConfigSerializer
    permission_classes = (AllowAny,)
    ordering_fields = ("created_at",)


class SyslogConfigViewSet(viewsets.ModelViewSet):
    queryset = SyslogConfig.objects.select_related("device").all()
    serializer_class = SyslogConfigSerializer
    permission_classes = (AllowAny,)
    ordering_fields = ("created_at",)


# ---------------------------------------------------------------------------
# SLB (LTM) ViewSets
# ---------------------------------------------------------------------------


class LtmVirtualServerViewSet(viewsets.ModelViewSet):
    from assets.models import LtmVirtualServer

    from .serializers import LtmVirtualServerSerializer

    queryset = LtmVirtualServer.objects.select_related("device").all()
    serializer_class = LtmVirtualServerSerializer
    permission_classes = (AllowAny,)
    search_fields = ("name", "vs_address", "vs_port", "pool", "device__hostname")
    ordering_fields = ("name", "device__hostname", "created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class LtmPoolViewSet(viewsets.ModelViewSet):
    from assets.models import LtmPool

    from .serializers import LtmPoolSerializer

    queryset = LtmPool.objects.select_related("device").all()
    serializer_class = LtmPoolSerializer
    permission_classes = (AllowAny,)
    search_fields = ("name", "mode", "device__hostname")
    ordering_fields = ("name", "device__hostname", "created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class LtmPoolMemberViewSet(viewsets.ModelViewSet):
    from assets.models import LtmPoolMember

    from .serializers import LtmPoolMemberSerializer

    queryset = LtmPoolMember.objects.select_related("device").all()
    serializer_class = LtmPoolMemberSerializer
    permission_classes = (AllowAny,)
    search_fields = ("name", "address", "pool_name", "device__hostname")
    ordering_fields = ("name", "pool_name", "created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class LtmProfileViewSet(viewsets.ModelViewSet):
    from assets.models import LtmProfile

    from .serializers import LtmProfileSerializer

    queryset = LtmProfile.objects.select_related("device").all()
    serializer_class = LtmProfileSerializer
    permission_classes = (AllowAny,)
    search_fields = ("name", "device__hostname")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class LtmIRuleViewSet(viewsets.ModelViewSet):
    from assets.models import LtmIRule

    from .serializers import LtmIRuleSerializer

    queryset = LtmIRule.objects.select_related("device").all()
    serializer_class = LtmIRuleSerializer
    permission_classes = (AllowAny,)
    search_fields = ("name", "device__hostname")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class LtmSNATViewSet(viewsets.ModelViewSet):
    from assets.models import LtmSNAT

    from .serializers import LtmSNATSerializer

    queryset = LtmSNAT.objects.select_related("device").all()
    serializer_class = LtmSNATSerializer
    permission_classes = (AllowAny,)
    search_fields = ("name", "device__hostname")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class LtmPersistViewSet(viewsets.ModelViewSet):
    from assets.models import LtmPersist

    from .serializers import LtmPersistSerializer

    queryset = LtmPersist.objects.select_related("device").all()
    serializer_class = LtmPersistSerializer
    permission_classes = (AllowAny,)
    search_fields = ("name", "device__hostname")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


# ---------------------------------------------------------------------------
# GSLB (GTM) ViewSets
# ---------------------------------------------------------------------------


class GtmDatacenterViewSet(viewsets.ModelViewSet):
    from assets.models import GtmDatacenter

    from .serializers import GtmDatacenterSerializer

    queryset = GtmDatacenter.objects.select_related("device").all()
    serializer_class = GtmDatacenterSerializer
    permission_classes = (AllowAny,)
    search_fields = ("name", "device__hostname")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class GtmWideipViewSet(viewsets.ModelViewSet):
    from assets.models import GtmWideip

    from .serializers import GtmWideipSerializer

    queryset = GtmWideip.objects.select_related("device").all()
    serializer_class = GtmWideipSerializer
    permission_classes = (AllowAny,)
    search_fields = ("name", "rtype", "lb_mode", "device__hostname")
    ordering_fields = ("name", "device__hostname", "created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class GtmPoolViewSet(viewsets.ModelViewSet):
    from assets.models import GtmPool

    from .serializers import GtmPoolSerializer

    queryset = GtmPool.objects.select_related("device").all()
    serializer_class = GtmPoolSerializer
    permission_classes = (AllowAny,)
    search_fields = ("name", "lb_mode", "fallback_ip", "device__hostname")
    ordering_fields = ("name", "device__hostname", "created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class GtmServerViewSet(viewsets.ModelViewSet):
    from assets.models import GtmServer

    from .serializers import GtmServerSerializer

    queryset = GtmServer.objects.select_related("device").all()
    serializer_class = GtmServerSerializer
    permission_classes = (AllowAny,)
    search_fields = ("name", "datacenter", "device__hostname")
    ordering_fields = ("name", "created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class GtmVServerViewSet(viewsets.ModelViewSet):
    from assets.models import GtmVServer

    from .serializers import GtmVServerSerializer

    queryset = GtmVServer.objects.select_related("device", "server").all()
    serializer_class = GtmVServerSerializer
    permission_classes = (AllowAny,)
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


# ---------------------------------------------------------------------------
# Firewall Policy ViewSets
# ---------------------------------------------------------------------------


class AddressBookViewSet(viewsets.ModelViewSet):
    from assets.models import AddressBook

    from .serializers import AddressBookSerializer

    queryset = AddressBook.objects.select_related("device", "parent").all()
    serializer_class = AddressBookSerializer
    permission_classes = (AllowAny,)
    search_fields = ("name", "device__hostname")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class ServiceViewSet(viewsets.ModelViewSet):
    from assets.models import Service

    from .serializers import ServiceSerializer

    queryset = Service.objects.select_related("device").all()
    serializer_class = ServiceSerializer
    permission_classes = (AllowAny,)
    search_fields = ("name", "protocol")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


class PolicyViewSet(viewsets.ModelViewSet):
    from assets.models import Policy

    from .serializers import PolicySerializer

    # 列表要展示源/目的地址（AddressBook）与端口（Service），三个 M2M 用 prefetch
    # 一次取回，避免逐行查询（N+1）
    queryset = (
        Policy.objects.select_related("device")
        .prefetch_related("source_addresses", "destination_addresses", "services")
        .all()
    )
    serializer_class = PolicySerializer
    permission_classes = (AllowAny,)
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


class NatRuleViewSet(viewsets.ModelViewSet):
    from assets.models import NatRule

    from .serializers import NatRuleSerializer

    queryset = NatRule.objects.select_related("device").all()
    serializer_class = NatRuleSerializer
    permission_classes = (AllowAny,)
    search_fields = ("name", "source_addresses__name", "destination_addresses__name", "device__hostname")
    ordering_fields = ("order", "created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs


# ---------------------------------------------------------------------------
# IPAM ViewSets
# ---------------------------------------------------------------------------


class TagViewSet(viewsets.ModelViewSet):
    from assets.models import Tag

    from .serializers import TagSerializer

    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = (AllowAny,)
    search_fields = ("name",)
    ordering_fields = ("name", "created_at")


class SubnetViewSet(viewsets.ModelViewSet):
    from assets.models import Subnet

    from .serializers import SubnetSerializer

    queryset = Subnet.objects.prefetch_related("tags").all()
    serializer_class = SubnetSerializer
    permission_classes = (AllowAny,)
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


class IPAddressViewSet(viewsets.ModelViewSet):
    from assets.models import IPAddress

    from .serializers import IPAddressSerializer

    queryset = IPAddress.objects.select_related("subnet", "device", "security_zone").all()
    serializer_class = IPAddressSerializer
    permission_classes = (AllowAny,)
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


class RouteViewSet(viewsets.ModelViewSet):
    from assets.models import Route

    from .serializers import RouteSerializer

    queryset = Route.objects.select_related("vrf", "vrf__device").all()
    serializer_class = RouteSerializer
    permission_classes = (AllowAny,)
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


class TopologyViewSet(viewsets.ModelViewSet):
    from assets.models import Topology

    from .serializers import TopologySerializer

    queryset = Topology.objects.all()
    serializer_class = TopologySerializer
    permission_classes = (AllowAny,)
    search_fields = ("name", "description")
    ordering_fields = ("name", "updated_at")


class ArpMacViewSet(viewsets.ModelViewSet):
    from assets.models import ArpMac

    from .serializers import ArpMacSerializer

    queryset = ArpMac.objects.select_related("device").all()
    serializer_class = ArpMacSerializer
    permission_classes = (AllowAny,)
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


class SubnetUsageLogViewSet(viewsets.ModelViewSet):
    from assets.models import SubnetUsageLog

    from .serializers import SubnetUsageLogSerializer

    queryset = SubnetUsageLog.objects.select_related("subnet").all()
    serializer_class = SubnetUsageLogSerializer
    permission_classes = (AllowAny,)
    ordering_fields = ("recorded_at", "utilization")

    def get_queryset(self):
        qs = super().get_queryset()
        subnet_id = self.request.query_params.get("subnet")
        if subnet_id:
            qs = qs.filter(subnet_id=subnet_id)
        return qs
