"""资产域的 MCP 关系边（``specs/`` 之外的独立一层）。

为什么边不跟着实体分文件：

- 边的归属天然模糊——``device → ltm_pool`` 既可以说属于「设备」，也可以说属于「LB」；
  按任一侧分，另一侧迟早要 import 对方的存在；
- 边只依赖 Django 模型与 ``NodeType``，**不 import 任何实体声明**，所以放在这一层
  永远不会和 ``specs/*.py`` 互相依赖；
- 36 条边在一屏多一点的范围，集中放能一眼看全图；等 VM / 物理机那批 IPAM 关联
  （弱匹配或 FK，见 ``ipam_links`` 规划）落地、边数过 60 再按关系主题拆成 ``edges/`` 包。

两条硬约束（写新边前先读）：

- **两端必须已在 ``specs/`` 里声明**，且 ``reverse`` 一定要给——影响面查询全靠反向边；
- **同一个 ``src`` 下边名必须唯一**：``registry.edge_named`` 只取第一条命中，
  重名会让 ``get_record(include=...)`` 静默串台（由 ``specs/__init__._validate_edges`` 兜住）。
"""

from assets import models
from llmtools.registry import Edge

from .nodes import NodeType


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


EDGES: tuple[Edge, ...] = (
    # —— 设备 → 台账 / IPAM ——
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
    # —— 设备 → SLB ——
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
    Edge(
        name="pool_members",
        src=NodeType.DEVICE,
        dst=NodeType.LTM_POOL_MEMBER,
        forward=_by_device(models.LtmPoolMember),
        reverse=lambda m: models.Device.objects.filter(pk=m.device_id),
    ),
    Edge(
        name="profiles",
        src=NodeType.DEVICE,
        dst=NodeType.LTM_PROFILE,
        forward=_by_device(models.LtmProfile),
        reverse=lambda p: models.Device.objects.filter(pk=p.device_id),
    ),
    Edge(
        name="irules",
        src=NodeType.DEVICE,
        dst=NodeType.LTM_IRULE,
        forward=_by_device(models.LtmIRule),
        reverse=lambda r: models.Device.objects.filter(pk=r.device_id),
    ),
    Edge(
        name="snats",
        src=NodeType.DEVICE,
        dst=NodeType.LTM_SNAT,
        forward=_by_device(models.LtmSNAT),
        reverse=lambda x: models.Device.objects.filter(pk=x.device_id),
    ),
    Edge(
        name="persists",
        src=NodeType.DEVICE,
        dst=NodeType.LTM_PERSIST,
        forward=_by_device(models.LtmPersist),
        reverse=lambda p: models.Device.objects.filter(pk=p.device_id),
    ),
    Edge(
        name="datacenters",
        src=NodeType.DEVICE,
        dst=NodeType.GTM_DATACENTER,
        forward=_by_device(models.GtmDatacenter),
        reverse=lambda d: models.Device.objects.filter(pk=d.device_id),
    ),
    Edge(
        name="gtm_pools",
        src=NodeType.DEVICE,
        dst=NodeType.GTM_POOL,
        forward=_by_device(models.GtmPool),
        reverse=lambda p: models.Device.objects.filter(pk=p.device_id),
    ),
    Edge(
        name="gtm_servers",
        src=NodeType.DEVICE,
        dst=NodeType.GTM_SERVER,
        forward=_by_device(models.GtmServer),
        reverse=lambda srv: models.Device.objects.filter(pk=srv.device_id),
    ),
    Edge(
        name="gtm_vservers",
        src=NodeType.DEVICE,
        dst=NodeType.GTM_VSERVER,
        forward=_by_device(models.GtmVServer),
        reverse=lambda v: models.Device.objects.filter(pk=v.device_id),
    ),
    # —— 设备 → 防火墙策略族 ——
    Edge(
        name="address_books",
        src=NodeType.DEVICE,
        dst=NodeType.ADDRESS_BOOK,
        forward=_by_device(models.AddressBook),
        reverse=lambda a: models.Device.objects.filter(pk=a.device_id),
    ),
    Edge(
        name="services",
        src=NodeType.DEVICE,
        dst=NodeType.SERVICE,
        forward=_by_device(models.Service),
        reverse=lambda svc: models.Device.objects.filter(pk=svc.device_id),
    ),
    Edge(
        name="policies",
        src=NodeType.DEVICE,
        dst=NodeType.POLICY,
        forward=_by_device(models.Policy),
        reverse=lambda p: models.Device.objects.filter(pk=p.device_id),
    ),
    Edge(
        name="nat_rules",
        src=NodeType.DEVICE,
        dst=NodeType.NAT_RULE,
        forward=_by_device(models.NatRule),
        reverse=lambda n: models.Device.objects.filter(pk=n.device_id),
    ),
    # —— 层级/引用关系：池成员靠「设备 + 池名」归属，没有外键 ——
    Edge(
        name="members",
        src=NodeType.LTM_POOL,
        dst=NodeType.LTM_POOL_MEMBER,
        forward=lambda pool: models.LtmPoolMember.objects.filter(device=pool.device, pool_name=pool.name),
        reverse=lambda m: models.LtmPool.objects.filter(device=m.device, name=m.pool_name),
    ),
    Edge(
        name="virtual_servers",
        src=NodeType.GTM_SERVER,
        dst=NodeType.GTM_VSERVER,
        forward=lambda srv: models.GtmVServer.objects.filter(server=srv),
        reverse=lambda v: models.GtmServer.objects.filter(pk=v.server_id),
    ),
    Edge(
        name="pools",
        src=NodeType.GTM_WIDEIP,
        dst=NodeType.GTM_POOL,
        # pools 是 JSON 名列表（老数据纯名字、新数据带权重），只能按名字在内存里匹配
        forward=lambda w: models.GtmPool.objects.filter(device=w.device, name__in=w.pool_names),
        reverse=lambda p: [w for w in models.GtmWideip.objects.filter(device=p.device) if p.name in w.pool_names],
    ),
    # —— 策略 / NAT 的地址与服务引用：影响面查询全靠 reverse ——
    Edge(
        name="source_addresses",
        src=NodeType.POLICY,
        dst=NodeType.ADDRESS_BOOK,
        forward=lambda p: p.source_addresses.all(),
        reverse=lambda a: models.Policy.objects.filter(source_addresses=a).distinct(),
    ),
    Edge(
        name="destination_addresses",
        src=NodeType.POLICY,
        dst=NodeType.ADDRESS_BOOK,
        forward=lambda p: p.destination_addresses.all(),
        reverse=lambda a: models.Policy.objects.filter(destination_addresses=a).distinct(),
    ),
    Edge(
        name="services",
        src=NodeType.POLICY,
        dst=NodeType.SERVICE,
        forward=lambda p: p.services.all(),
        reverse=lambda svc: models.Policy.objects.filter(services=svc).distinct(),
    ),
    Edge(
        name="source_addresses",
        src=NodeType.NAT_RULE,
        dst=NodeType.ADDRESS_BOOK,
        forward=lambda n: n.source_addresses.all(),
        reverse=lambda a: models.NatRule.objects.filter(source_addresses=a).distinct(),
    ),
    Edge(
        name="destination_addresses",
        src=NodeType.NAT_RULE,
        dst=NodeType.ADDRESS_BOOK,
        forward=lambda n: n.destination_addresses.all(),
        reverse=lambda a: models.NatRule.objects.filter(destination_addresses=a).distinct(),
    ),
    Edge(
        name="services",
        src=NodeType.NAT_RULE,
        dst=NodeType.SERVICE,
        forward=lambda n: n.services.all(),
        reverse=lambda svc: models.NatRule.objects.filter(services=svc).distinct(),
    ),
    Edge(
        name="translated_source",
        src=NodeType.NAT_RULE,
        dst=NodeType.ADDRESS_BOOK,
        forward=lambda n: [n.translated_source] if n.translated_source else [],
        reverse=lambda a: models.NatRule.objects.filter(translated_source=a),
    ),
    Edge(
        name="translated_destination",
        src=NodeType.NAT_RULE,
        dst=NodeType.ADDRESS_BOOK,
        forward=lambda n: [n.translated_destination] if n.translated_destination else [],
        reverse=lambda a: models.NatRule.objects.filter(translated_destination=a),
    ),
    Edge(
        name="translated_service",
        src=NodeType.NAT_RULE,
        dst=NodeType.SERVICE,
        forward=lambda n: [n.translated_service] if n.translated_service else [],
        reverse=lambda svc: models.NatRule.objects.filter(translated_service=svc),
    ),
)


__all__ = ["EDGES"]
