"""资产域的 MCP 实体声明（import 即注册到 core.mcp.registry）。

通用工具（``core.mcp.tools``）只认注册表，不认具体域；本模块负责把资产的模型
翻译成 ``EntitySpec``，并登记类型之间的关系边。新增一张表只加一条 spec，
工具层零改动。

三条约束（改本文件前先读）：

- **摘要字段名必须是序列化器里存在的键**。字段口径复用 ``assets.serializers``
  （与 REST API 同一套），不在工具层另造字段名；漏写只是少一个字段
  （``to_dict`` 用 ``.get`` 取），不会抛异常，但会静默丢信息。
- **过滤操作符走白名单**。``list_records`` 不接受任意 ``__`` 查找。
- **边的两端必须是已登记类型，且 ``reverse`` 一定要给**。影响面查询全靠反向边。
"""

import re

from django.db.models import Q

from assets import models
from assets.serializers import views as s
from core.mcp.registry import EDGES, SPEC, Edge, EntitySpec, Filter, register_edge, register_entity


class NodeType:
    """资产域的节点类型标识。

    **刻意不用 ``models.TextChoices``**：``Enum`` 的 ``__hash__`` 按成员名取哈希，
    于是 ``NodeType.DEVICE`` 和 ``"device"`` 相等却哈希不同，作为 ``dict`` 键查不到。
    这里要的是普通字符串常量。
    """

    DEVICE = "device"
    DEVICE_GROUP = "device_group"
    INTERFACE = "interface"
    VLAN = "vlan"
    VRF = "vrf"
    ROUTE = "route"
    SUBNET = "subnet"
    IP_ADDRESS = "ip_address"
    ARP_MAC = "arp_mac"
    LTM_VIRTUAL_SERVER = "ltm_virtual_server"
    LTM_POOL = "ltm_pool"
    GTM_WIDEIP = "gtm_wideip"


# ---------------------------------------------------------------------------
# MAC 归一化（资产域特有：ARP 表存的是原始串）
# ---------------------------------------------------------------------------


def _mac_compact(text: str) -> str:
    """去掉分隔符后的 12 位小写十六进制；不是 MAC 形态返回空串。

    三种写法（``aa-bb-cc-dd-ee-ff`` / ``aabb.ccdd.eeff`` / ``AA:BB:CC``）都出现过，
    不先归一化，MAC 查询十次有九次查不到。
    """
    compact = re.sub(r"[^0-9a-fA-F]", "", text or "").lower()
    return compact if len(compact) == 12 else ""


def _mac_variants(compact: str) -> list[str]:
    pairs = [compact[i : i + 2] for i in range(0, 12, 2)]
    # 点分形态是 3 组、每组 4 个十六进制（aabb.ccdd.eeff），所以按「两对一拼」走 0/2/4
    dotted = ".".join("".join(pairs[i : i + 2]) for i in range(0, 6, 2))
    return list(dict.fromkeys([":".join(pairs), "-".join(pairs), dotted, compact]))


def _arp_extra_search(text: str) -> list[Q]:
    """MAC 三种分隔符归一后的额外匹配条件（挂到 arp_mac 的 spec 上）。"""
    compact = _mac_compact(text)
    if not compact:
        return []
    return [Q(mac_address__iexact=variant) for variant in _mac_variants(compact)]


# ---------------------------------------------------------------------------
# 实体声明
# ---------------------------------------------------------------------------

_BUNDLE: dict[str, EntitySpec] = {
    NodeType.DEVICE: EntitySpec(
        node_type=NodeType.DEVICE,
        label="网络设备",
        model=models.Device,
        serializer=s.DeviceSerializer,
        key="hostname",
        summary=("hostname", "device_type", "device_type_display", "ip_address", "idc_name", "security_zone_name"),
        filters={
            "keyword": Filter(("hostname", "ip_address", "remark")),
            "device_type": Filter(("device_type",), "exact"),
            "vendor": Filter(("device_model__vendor__name",)),
            "group": Filter(("group_memberships__group__name",)),
            "idc": Filter(("idc__name",)),
            "security_zone": Filter(("security_zone__name",)),
        },
        search=("hostname", "ip_address", "remark"),
        select_related=("device_model__vendor", "idc", "cabinet__room", "security_zone"),
        order=("hostname",),
        default_sections=("groups", "interfaces", "ip_addresses", "arp"),
    ),
    NodeType.DEVICE_GROUP: EntitySpec(
        node_type=NodeType.DEVICE_GROUP,
        label="设备组",
        model=models.DeviceGroup,
        serializer=s.DeviceGroupSerializer,
        key="name",
        summary=("name", "group_type", "group_type_display", "description", "device_role"),
        filters={"keyword": Filter(("name", "description"))},
        search=("name", "description"),
        prefetch=("members__device",),
        order=("name",),
    ),
    NodeType.INTERFACE: EntitySpec(
        node_type=NodeType.INTERFACE,
        label="接口",
        model=models.Interface,
        serializer=s.InterfaceSerializer,
        key="interface",
        summary=("device_hostname", "interface", "mode", "ip_address", "enabled", "description"),
        filters={
            "keyword": Filter(("interface", "description", "ip_address")),
            "device": Filter(("device__hostname",)),
            "mode": Filter(("mode",), "exact"),
        },
        search=("interface", "description", "ip_address"),
        scoped=True,
        select_related=("device", "vrf"),
        order=("device__hostname", "interface"),
    ),
    NodeType.VLAN: EntitySpec(
        node_type=NodeType.VLAN,
        label="VLAN",
        model=models.Vlan,
        serializer=s.VlanSerializer,
        key="vid",
        summary=("device_hostname", "vid", "name", "description"),
        filters={"device": Filter(("device__hostname",)), "vid": Filter(("vid",), "exact")},
        scoped=True,
        select_related=("device",),
        order=("device__hostname", "vid"),
    ),
    NodeType.VRF: EntitySpec(
        node_type=NodeType.VRF,
        label="VRF",
        model=models.Vrf,
        serializer=s.VrfSerializer,
        key="name",
        summary=("device_hostname", "name", "rd", "description"),
        filters={"device": Filter(("device__hostname",)), "keyword": Filter(("name", "rd"))},
        search=("name", "rd"),
        scoped=True,
        select_related=("device",),
        order=("device__hostname", "name"),
    ),
    NodeType.ROUTE: EntitySpec(
        node_type=NodeType.ROUTE,
        label="路由",
        model=models.Route,
        serializer=s.RouteSerializer,
        key="destination",
        summary=("device_hostname", "destination", "nexthop", "interface", "protocol", "metric"),
        filters={
            "device": Filter(("device__hostname",)),
            "vrf": Filter(("vrf__name",)),
            "keyword": Filter(("destination", "nexthop", "interface")),
            "protocol": Filter(("protocol",), "exact"),
        },
        search=("destination", "nexthop"),
        scoped=True,
        select_related=("device", "vrf"),
        order=("device__hostname", "destination"),
    ),
    NodeType.SUBNET: EntitySpec(
        node_type=NodeType.SUBNET,
        label="子网",
        model=models.Subnet,
        serializer=s.SubnetSerializer,
        key="network",
        summary=("network", "vlan", "gateway", "vrf", "description"),
        filters={
            "keyword": Filter(("network", "description", "vlan")),
            "vlan": Filter(("vlan",), "exact"),
            "vrf": Filter(("vrf",), "exact"),
        },
        search=("network", "description"),
        select_related=("datacenter", "security_zone"),
        order=("network",),
    ),
    NodeType.IP_ADDRESS: EntitySpec(
        node_type=NodeType.IP_ADDRESS,
        label="IP地址",
        model=models.IPAddress,
        serializer=s.IPAddressSerializer,
        key="ip_address",
        summary=("ip_address", "status", "device_hostname", "interface", "description"),
        filters={
            "keyword": Filter(("ip_address", "description")),
            "subnet": Filter(("subnet__network",)),
            "status": Filter(("status",), "exact"),
            "device": Filter(("device__hostname",)),
        },
        search=("ip_address", "description"),
        select_related=("subnet", "device", "security_zone"),
        order=("ip_address",),
    ),
    NodeType.ARP_MAC: EntitySpec(
        node_type=NodeType.ARP_MAC,
        label="ARP/MAC",
        model=models.ArpMac,
        serializer=s.ArpMacSerializer,
        key="ip_address",
        summary=("device_hostname", "ip_address", "mac_address", "vlan", "interface", "arp_type", "status"),
        filters={
            "keyword": Filter(("ip_address", "mac_address", "interface")),
            "device": Filter(("device__hostname",)),
            "vlan": Filter(("vlan",), "exact"),
            "status": Filter(("status",), "exact"),
        },
        search=("ip_address", "mac_address", "interface"),
        # 业务键是 设备+IP+MAC 三件套，单靠 ip 取不唯一
        gettable=False,
        select_related=("device",),
        order=("device__hostname", "ip_address"),
        extra_search=_arp_extra_search,
    ),
    NodeType.LTM_VIRTUAL_SERVER: EntitySpec(
        node_type=NodeType.LTM_VIRTUAL_SERVER,
        label="负载均衡虚拟服务器",
        model=models.LtmVirtualServer,
        serializer=s.LtmVirtualServerSerializer,
        key="name",
        summary=("device_hostname", "name", "vs_address", "vs_port", "pool", "status"),
        filters={
            "keyword": Filter(("name", "vs_address", "pool")),
            "device": Filter(("device__hostname",)),
        },
        search=("name", "vs_address"),
        scoped=True,
        select_related=("device",),
        order=("device__hostname", "name"),
    ),
    NodeType.LTM_POOL: EntitySpec(
        node_type=NodeType.LTM_POOL,
        label="负载均衡池",
        model=models.LtmPool,
        serializer=s.LtmPoolSerializer,
        key="name",
        summary=("device_hostname", "name", "mode"),
        filters={"keyword": Filter(("name",)), "device": Filter(("device__hostname",))},
        search=("name",),
        scoped=True,
        select_related=("device",),
        order=("device__hostname", "name"),
    ),
    NodeType.GTM_WIDEIP: EntitySpec(
        node_type=NodeType.GTM_WIDEIP,
        label="全局负载域名",
        model=models.GtmWideip,
        serializer=s.GtmWideipSerializer,
        key="name",
        summary=("device_hostname", "name", "rtype", "lb_mode"),
        filters={"keyword": Filter(("name",)), "device": Filter(("device__hostname",))},
        search=("name",),
        scoped=True,
        select_related=("device",),
        order=("device__hostname", "name"),
    ),
}


# ---------------------------------------------------------------------------
# 边
# ---------------------------------------------------------------------------


def _by_device(model: type):
    return lambda device: model.objects.filter(device=device)


def _groups_with_role(device):
    """设备所属的组，顺带把「设备在该组里的角色」挂到对象上。

    角色属于 membership（``DeviceGroupMember.device_role``），不属于组本身；
    不挂这一下，``get_record(device, include="groups")`` 就只剩组名，恰好丢掉
    「它是主还是备」这个最常被问的信息。
    """
    for membership in device.group_memberships.select_related("group"):
        group = membership.group
        group._mcp_extra = {"device_role": membership.device_role}
        yield group


_EDGES: tuple[Edge, ...] = (
    Edge(
        name="groups",
        src=NodeType.DEVICE,
        dst=NodeType.DEVICE_GROUP,
        forward=_groups_with_role,
        reverse=lambda g: models.Device.objects.filter(group_memberships__group=g).distinct(),
    ),
    Edge(
        name="interfaces",
        src=NodeType.DEVICE,
        dst=NodeType.INTERFACE,
        forward=_by_device(models.Interface),
        reverse=lambda i: models.Device.objects.filter(pk=i.device_id),
    ),
    Edge(
        name="vlans",
        src=NodeType.DEVICE,
        dst=NodeType.VLAN,
        forward=_by_device(models.Vlan),
        reverse=lambda v: models.Device.objects.filter(pk=v.device_id),
    ),
    Edge(
        name="vrfs",
        src=NodeType.DEVICE,
        dst=NodeType.VRF,
        forward=_by_device(models.Vrf),
        reverse=lambda v: models.Device.objects.filter(pk=v.device_id),
    ),
    Edge(
        name="vrfs",
        src=NodeType.VRF,
        dst=NodeType.ROUTE,
        forward=lambda v: models.Route.objects.filter(vrf=v),
        reverse=lambda r: models.Vrf.objects.filter(pk=r.vrf_id),
    ),
    Edge(
        name="ip_addresses",
        src=NodeType.DEVICE,
        dst=NodeType.IP_ADDRESS,
        forward=_by_device(models.IPAddress),
        reverse=lambda ip: models.Device.objects.filter(pk=ip.device_id) if ip.device_id else [],
    ),
    Edge(
        name="ip_addresses",
        src=NodeType.SUBNET,
        dst=NodeType.IP_ADDRESS,
        forward=lambda net: models.IPAddress.objects.filter(subnet=net),
        reverse=lambda ip: models.Subnet.objects.filter(pk=ip.subnet_id) if ip.subnet_id else [],
    ),
    Edge(
        name="arp",
        src=NodeType.DEVICE,
        dst=NodeType.ARP_MAC,
        forward=_by_device(models.ArpMac),
        reverse=lambda a: models.Device.objects.filter(pk=a.device_id),
    ),
    Edge(
        name="virtual_servers",
        src=NodeType.DEVICE,
        dst=NodeType.LTM_VIRTUAL_SERVER,
        forward=_by_device(models.LtmVirtualServer),
        reverse=lambda v: models.Device.objects.filter(pk=v.device_id),
    ),
    Edge(
        name="pools",
        src=NodeType.DEVICE,
        dst=NodeType.LTM_POOL,
        forward=_by_device(models.LtmPool),
        reverse=lambda p: models.Device.objects.filter(pk=p.device_id),
    ),
    Edge(
        name="wideips",
        src=NodeType.DEVICE,
        dst=NodeType.GTM_WIDEIP,
        forward=_by_device(models.GtmWideip),
        reverse=lambda w: models.Device.objects.filter(pk=w.device_id),
    ),
)


def register() -> None:
    """把本域实体与边登记到 core.mcp.registry（模块 import 时自动调用一次）。"""
    for spec in _BUNDLE.values():
        if spec.node_type not in SPEC:
            register_entity(spec)
    for edge in _EDGES:
        if not any(e.name == edge.name and e.src == edge.src and e.dst == edge.dst for e in EDGES):
            register_edge(edge)


register()


__all__ = [
    "EDGES",
    "SPEC",
    "NodeType",
    "register",
]
