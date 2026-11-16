"""资产总览的跨域聚合（``/api/assets/overview/``）。

Home 页的一次请求要同时看**资产**（机柜 / 设备 / 网段）与**配置行**（接口 / VLAN /
路由 / 策略 / NAT / SLB / GTM / ARP）的分布。这是全项目唯一在读取侧同时消费两个域的
查询：assets 是叶子节点（矩阵禁止 ``assets → configs``），configs 也不该反过来读 assets
的设备 / 机柜，所以聚合只能落在两者之上——按依赖矩阵 ``analysis → ingest → configs →
assets``，最自然的落点就是 analysis（它本来就有 dashboard / lb-chain / 设备组合并这些
跨域只读聚合）。

**URL 与 name 保持拆分前的 ``/api/assets/overview/``（``assets-overview``）**：路由跟着
view 走、不跟 app 走，前端 ``views/Home.vue`` 与已有反解零改动（同 ``access-flows``
从 ingest 迁入时的做法）。

口径就是「按字段分组计数」：只读、无缓存、无写操作。单个 count 走索引，68 次查询在
内网毫秒级；真成瓶颈时再谈缓存，别提前加。
"""

from django.db.models import Count
from rest_framework.decorators import api_view
from rest_framework.response import Response

from assets.models import Cabinet, DataCenter, Device, DeviceModel, Room, SecurityZone, Subnet, Vendor
from configs.models import (
    AddressBook,
    ArpMac,
    GtmDatacenter,
    GtmPool,
    GtmWideip,
    Interface,
    LtmPool,
    LtmPoolMember,
    LtmVirtualServer,
    NatRule,
    Policy,
    Route,
    Service,
    Vlan,
    Vrf,
)


@api_view(["GET"])
def assets_overview(request):
    """资产 + 配置行概览统计（Home 页卡片）。"""
    # 基础设施
    cabinets_by_dc = list(Cabinet.objects.values("room__datacenter__name").annotate(count=Count("id")).order_by("-count")[:10])
    cabinets_by_status = list(Cabinet.objects.values("status").annotate(count=Count("id")))

    # 设备
    device_types = list(Device.objects.values("device_type").annotate(count=Count("id")).order_by("-count"))
    devices_by_vendor = list(Device.objects.values("device_model__vendor__name").annotate(count=Count("id")).order_by("-count")[:10])
    devices_by_zone = list(Device.objects.values("security_zone__name").annotate(count=Count("id")).order_by("-count"))

    # 接口
    interface_modes = list(Interface.objects.values("mode").annotate(count=Count("id")))

    # 路由
    route_protocols = list(Route.objects.values("protocol").annotate(count=Count("id")).order_by("-count"))
    routes_by_device = list(Route.objects.values("vrf__device__hostname").annotate(count=Count("id")).order_by("-count")[:10])

    # 防火墙
    policies_by_action = list(Policy.objects.values("action").annotate(count=Count("id")))
    nat_by_type = list(NatRule.objects.values("nat_type").annotate(count=Count("id")))
    address_books_by_type = list(AddressBook.objects.values("address_type").annotate(count=Count("id")))
    services_by_protocol = list(Service.objects.values("protocol").annotate(count=Count("id")))

    # IPAM
    subnets_by_dc = list(Subnet.objects.values("datacenter__name").annotate(count=Count("id")).order_by("-count"))
    subnets_by_zone = list(Subnet.objects.values("security_zone__name").annotate(count=Count("id")).order_by("-count"))

    # SLB
    vs_by_protocol = list(LtmVirtualServer.objects.values("protocol").annotate(count=Count("id")))
    pools_by_lb = list(LtmPool.objects.values("device__hostname").annotate(count=Count("id")).order_by("-count")[:10])

    return Response(
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
