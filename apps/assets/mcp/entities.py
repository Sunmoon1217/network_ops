"""实体注册表（MCP 工具的数据面）。

工具函数只有 6 个，实体表有 40+ 张。让两者不一起膨胀的办法是**把工具退化成数据**：
新增一张表只加一条 ``EntitySpec``，不加工具、不改工具签名。

本模块是三处共用的唯一真源：

1. ``NodeType``：跨域节点类型枚举。``PortLink`` / ``EntityRelation`` 这类「边表」
   与 ``EDGES`` 声明都用它，避免将来出现 ``physical_server`` 与 ``physicalserver``
   两种写法并存。
2. ``SPEC``：每个类型的模型、序列化器、业务键、摘要字段、可过滤字段。
3. ``EDGES``：类型之间的边（谁连谁、正反两个方向怎么查）。``get_record`` 的
   ``include`` 与 ``relations`` 的遍历**共用**这张表，不各写一份——否则两头会漂。

改动本文件前先读这三条约束：

- **摘要字段名必须是序列化器里存在的键**。字段口径复用 ``assets.serializers``
  （与 REST API 同一套），不在工具层另造一套字段名；漏写只是少一个字段
  （``to_dict`` 用 ``.get`` 取），不会抛异常，但会静默丢信息。
- **过滤操作符走白名单**。``list_records`` 不接受任意 ``__`` 查找——把 ORM 语法
  直接暴露给 LLM，等于放弃参数校验。
- **边的两端必须是已登记类型，且 ``reverse`` 一定要给**。影响面查询（谁依赖我）
  全靠反向边，只写正向的边等于没有图。

边表尚未落库（``PortLink`` / ``EntityRelation``）：服务器、数据库、应用系统的表还没
建，先把 ``NodeType`` 占位登记。表建好之后在这里补 4 条 spec + 几条 edge 即可，
工具层零改动——这正是本模块存在的意义。
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from django.db.models import Q, QuerySet
from mcp.server.mcpserver.exceptions import ToolError

from assets import models
from assets.serializers import views as s

# ---------------------------------------------------------------------------
# 节点类型
# ---------------------------------------------------------------------------


class NodeType:
    """节点类型标识。

    **刻意不用 ``models.TextChoices``**：``Enum`` 的 ``__hash__`` 按成员名取哈希，
    于是 ``NodeType.DEVICE`` 和 ``"device"`` 相等却哈希不同，作为 ``dict`` 键查不到
    ——``SPEC[NodeType.DEVICE]`` 会静默 KeyError。这里要的是普通字符串常量。

    将来建 ``PortLink`` / ``EntityRelation`` 时用 ``choices=NodeType.CHOICES``，
    一处定义处处受约束。**预留项**（physical_server 等）表尚未建立，只是先占住拼写，
    避免几个月后同时出现 ``physical_server`` 与 ``physicalserver`` 两种写法。
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
    # 预留：表未建，先占位（见模块注释）
    PHYSICAL_SERVER = "physical_server"
    VIRTUAL_SERVER = "virtual_server"
    DATABASE_INSTANCE = "database_instance"
    APPLICATION_SYSTEM = "application_system"

    CHOICES = (
        (DEVICE, "网络设备"),
        (DEVICE_GROUP, "设备组"),
        (INTERFACE, "接口"),
        (VLAN, "VLAN"),
        (VRF, "VRF"),
        (ROUTE, "路由"),
        (SUBNET, "子网"),
        (IP_ADDRESS, "IP地址"),
        (ARP_MAC, "ARP/MAC"),
        (LTM_VIRTUAL_SERVER, "负载均衡虚拟服务器"),
        (LTM_POOL, "负载均衡池"),
        (GTM_WIDEIP, "全局负载域名"),
        (PHYSICAL_SERVER, "物理服务器"),
        (VIRTUAL_SERVER, "虚拟服务器"),
        (DATABASE_INSTANCE, "数据库实例"),
        (APPLICATION_SYSTEM, "应用系统"),
    )


# ---------------------------------------------------------------------------
# 过滤与实体描述
# ---------------------------------------------------------------------------

MAX_PAGE_SIZE = 100
MAX_DEPTH = 4


@dataclass(frozen=True)
class Filter:
    """一个对外暴露的过滤条件。

    ``fields`` 是多字段时按 **OR** 组合（例如 keyword 同时匹配主机名/管理IP/备注）；
    ``op`` 只允许下列白名单，不做任意 lookup 透传。
    """

    fields: tuple[str, ...]
    op: str = "icontains"

    def build(self, value: Any) -> Q:
        if self.op == "in":
            if not isinstance(value, (list, tuple)):
                value = [value]
            parts = [Q(**{f"{f}__in": list(value)}) for f in self.fields]
        elif self.op == "isnull":
            parts = [Q(**{f"{f}__isnull": bool(value)}) for f in self.fields]
        elif self.op in {"exact", "icontains", "istartswith", "gte", "lte"}:
            parts = [Q(**{f"{f}__{self.op}": value}) for f in self.fields]
        else:  # pragma: no cover - 白名单外的 op 是编码错误，不是用户输入错误
            raise ValueError(f"不支持的过滤操作符：{self.op}")
        cond = parts[0]
        for part in parts[1:]:
            cond |= part
        return cond


@dataclass(frozen=True)
class EntitySpec:
    """一个实体类型在工具层的全部描述。

    ``scoped=True`` 表示该模型挂在设备下（``ConfigBase`` 子类）：业务键只在单台设备
    内唯一，所以 ``get_record`` 必须带 ``device`` 限定。这不是为了严格，而是因为
    ``interface`` 叫 ``Gi1/0/1`` 的接口在每台交换机上都有——不带设备就查等于瞎猜。
    """

    node_type: str
    label: str
    model: type
    serializer: type
    key: str
    summary: tuple[str, ...]
    filters: dict[str, Filter] = field(default_factory=dict)
    search: tuple[str, ...] = ()
    scoped: bool = False
    #: False 表示业务键不唯一（如 ARP 表按 设备+IP+MAC 唯一），不能直接 get
    gettable: bool = True
    select_related: tuple[str, ...] = ()
    prefetch: tuple[str, ...] = ()
    order: tuple[str, ...] = ()
    #: 权限钩子：接上用户身份后由这里返回「按 request 过滤」的 queryset；
    #: 内网可信部署保持 None，编译器退回全库（权限永远不来自调用方输入）。
    base_queryset: Callable[[Any], QuerySet] | None = None

    def queryset(self, base: QuerySet | None = None) -> QuerySet:
        qs = base if base is not None else self.model.objects.all()
        if self.select_related:
            qs = qs.select_related(*self.select_related)
        if self.prefetch:
            qs = qs.prefetch_related(*self.prefetch)
        if self.order:
            qs = qs.order_by(*self.order)
        return qs


SPEC: dict[str, EntitySpec] = {
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


def get_spec(node_type: str) -> EntitySpec:
    """取实体描述；类型不存在时把**可用类型**回给调用方。

    错误信息里带合法值是粗粒度工具的必要条件：LLM 猜错 ``entity_type`` 时，
    这条错误是它唯一的纠正信号。
    """
    spec = SPEC.get((node_type or "").strip())
    if spec is None:
        options = " / ".join(sorted(SPEC))
        raise ToolError(f"未知的 entity_type：{node_type or '(空)'}；可选值 {options}")
    return spec


def parse_filters(spec: EntitySpec, raw: dict[str, Any] | None) -> list[tuple[str, Any]]:
    """校验并归一化过滤参数，返回 ``[(名字, 值)]``。

    未声明的键直接报错而不是忽略——静默忽略会让 LLM 以为过滤生效了，从而给出
    范围过宽的结论。
    """
    if not raw:
        return []
    unknown = sorted(set(raw) - set(spec.filters))
    if unknown:
        options = " / ".join(sorted(spec.filters)) or "(无)"
        raise ToolError(f"{spec.node_type} 不支持的过滤字段：{', '.join(unknown)}；可选值 {options}")
    return [(name, raw[name]) for name in raw if raw[name] not in (None, "", [])]


def apply_filters(spec: EntitySpec, qs: QuerySet, items: Iterable[tuple[str, Any]]) -> tuple[QuerySet, bool]:
    """把过滤条件贴到 queryset 上，返回 ``(qs, 是否用过过滤)``。"""
    used = False
    for name, value in items:
        qs = qs.filter(spec.filters[name].build(value))
        used = True
    # 过滤路径可能穿过 to-many（device.group_memberships），必须去重
    return (qs.distinct() if used else qs), used


# ---------------------------------------------------------------------------
# 序列化口径
# ---------------------------------------------------------------------------


def summary_fields(spec: EntitySpec) -> tuple[str, ...]:
    """摘要字段：id + 业务键 + 声明字段，去重保序。"""
    return tuple(dict.fromkeys(("id", spec.key, *spec.summary)))


def to_dict(spec: EntitySpec, obj: Any, *, full: bool = False) -> dict[str, Any]:
    """按序列化器口径输出。

    ``full=False`` 只留摘要——列表层返回全字段是 token 浪费的主要来源：
    设备 18 个字段 × 20 条 = 360 个字段的噪音，而 LLM 下一步只会用到其中两三个。

    边的解析器若在对象上挂了 ``_mcp_extra``（见 ``EDGES`` 的 ``groups``），
    这里合并进来。用它是因为「设备在组里的角色」属于 membership 而不是 group，
    为此新建一个 ``device_group_member`` 节点类型会把图搞脏。
    """
    data = dict(spec.serializer(obj).data)
    extra = getattr(obj, "_mcp_extra", None)
    if extra:
        data.update(extra)
    if full:
        return data
    return {name: data[name] for name in summary_fields(spec) if name in data}


def key_value(spec: EntitySpec, obj: Any) -> str:
    value = getattr(obj, spec.key, "")
    return "" if value is None else str(value)


def resolve_one(spec: EntitySpec, key: str, device: str = "") -> Any:
    """按业务键取单条（scoped 类型必须给 device）。"""
    text = (key or "").strip()
    if not text:
        raise ToolError(f"{spec.node_type} 的 key 不能为空（业务键是 {spec.key}）")
    qs = spec.queryset()
    if spec.scoped:
        if not device:
            raise ToolError(f"{spec.node_type} 需要 device 参数（主机名）限定：{spec.key} 只在单台设备内唯一")
        qs = qs.filter(device__hostname__iexact=device.strip())
    if text.isdigit():
        hit = qs.filter(pk=int(text)).first()
        if hit is not None:
            return hit
    if not spec.gettable:
        raise ToolError(
            f"{spec.label}不能按 {spec.key} 直接取：它不唯一（真实键是 设备+{spec.key}+更多字段）。"
            f"请用 list_records(entity_type='{spec.node_type}', filters=...)、locate，或传数字主键 id"
        )
    hit = qs.filter(**{f"{spec.key}__iexact": text}).first()
    if hit is None:
        options = " / ".join(sorted(spec.filters)) or "(无)"
        raise ToolError(
            f"{spec.label}不存在：{text}；{spec.key} 需精确匹配，"
            f"可先用 find 定位，或用 list_records(entity_type='{spec.node_type}') 按 {options} 过滤"
        )
    return hit


# ---------------------------------------------------------------------------
# 边
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Edge:
    """一条有向边。

    ``forward`` 与 ``reverse`` 都返回**对象可迭代**，用显式 queryset 而不是 Django
    的反向访问器（``device.interface_set``）——访问器名由模型类名推导，改名即断，
    且 ``ConfigBase`` 没给 ``related_name``，靠猜不是办法。
    """

    name: str
    src: str
    dst: str
    forward: Callable[[Any], Iterable[Any]]
    reverse: Callable[[Any], Iterable[Any]]


def _by_device(model: type) -> Callable[[Any], QuerySet]:
    return lambda device: model.objects.filter(device=device)


def _groups_with_role(device: Any):
    """设备所属的组，顺带把「设备在该组里的角色」挂到对象上。

    角色属于 membership（``DeviceGroupMember.device_role``），不属于组本身；
    不挂这一下，``get_record(device, include="groups")`` 就只剩组名，恰好丢掉
    「它是主还是备」这个最常被问的信息。
    """
    for membership in device.group_memberships.select_related("group"):
        group = membership.group
        group._mcp_extra = {"device_role": membership.device_role}
        yield group


EDGES: tuple[Edge, ...] = (
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


def edges_from(node_type: str) -> list[Edge]:
    return [e for e in EDGES if e.src == node_type]


def edges_to(node_type: str) -> list[Edge]:
    return [e for e in EDGES if e.dst == node_type]


def edge_named(node_type: str, name: str) -> Edge:
    """取某个类型上名为 ``name`` 的正向边（``get_record`` 的 include 用）。"""
    for edge in edges_from(node_type):
        if edge.name == name:
            return edge
    options = " / ".join(sorted({e.name for e in edges_from(node_type)}))
    raise ToolError(f"{node_type} 不支持 include：{name}；可选值 {options or '(无)'}")


def edge_options(node_type: str) -> list[str]:
    return sorted({e.name for e in edges_from(node_type)})


__all__ = [
    "EDGES",
    "MAX_DEPTH",
    "MAX_PAGE_SIZE",
    "SPEC",
    "Edge",
    "EntitySpec",
    "Filter",
    "NodeType",
    "apply_filters",
    "edge_named",
    "edge_options",
    "edges_from",
    "edges_to",
    "get_spec",
    "key_value",
    "parse_filters",
    "resolve_one",
    "summary_fields",
    "to_dict",
]
