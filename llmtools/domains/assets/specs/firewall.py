"""防火墙策略族实体：地址簿 / 服务簿 / 安全策略 / NAT 规则。

策略与 NAT 对地址簿、服务的引用（M2M 与「转换后」FK）声明在 ``../edges.py``，
影响面查询（「这个地址簿被哪些策略引用」）全靠那些边的 ``reverse``。
"""

from assets import models
from assets.serializers import views as s
from llmtools.registry import EntitySpec, Filter

from ..nodes import NodeType

BUNDLE: dict[str, EntitySpec] = {
    NodeType.ADDRESS_BOOK: EntitySpec(
        node_type=NodeType.ADDRESS_BOOK,
        label="地址簿",
        model=models.AddressBook,
        serializer=s.AddressBookSerializer,
        key="name",
        summary=("device_hostname", "name", "address_type", "ip_address", "ip_netmask", "ip_start", "ip_end", "parent_name"),
        filters={
            "keyword": Filter(("name", "ip_address", "description")),
            "device": Filter(("device__hostname",)),
            "address_type": Filter(("address_type",), "exact"),
        },
        search=("name", "ip_address"),
        scoped=True,
        select_related=("device", "parent"),
        order=("device__hostname", "name"),
    ),
    NodeType.SERVICE: EntitySpec(
        node_type=NodeType.SERVICE,
        label="服务簿",
        model=models.Service,
        serializer=s.ServiceSerializer,
        key="name",
        summary=("device_hostname", "name", "protocol", "port", "port2", "description"),
        filters={
            "keyword": Filter(("name", "port")),
            "device": Filter(("device__hostname",)),
            "protocol": Filter(("protocol",), "exact"),
        },
        search=("name", "port"),
        scoped=True,
        # 自然键是 设备+名+协议+端口：一个服务名允许多行端口定义
        gettable=False,
        select_related=("device",),
        order=("device__hostname", "name"),
    ),
    NodeType.POLICY: EntitySpec(
        node_type=NodeType.POLICY,
        label="防火墙策略",
        model=models.Policy,
        serializer=s.PolicySerializer,
        key="policy_id",
        summary=("device_hostname", "policy_id", "order", "name", "action", "enabled", "description"),
        filters={
            "keyword": Filter(("policy_id", "name", "description")),
            "device": Filter(("device__hostname",)),
            "action": Filter(("action",), "exact"),
            "enabled": Filter(("enabled",), "exact"),
        },
        search=("policy_id", "name"),
        scoped=True,
        select_related=("device",),
        prefetch=("source_addresses", "destination_addresses", "services"),
        order=("device__hostname", "order"),
    ),
    NodeType.NAT_RULE: EntitySpec(
        node_type=NodeType.NAT_RULE,
        label="NAT 规则",
        model=models.NatRule,
        serializer=s.NatRuleSerializer,
        key="name",
        summary=("device_hostname", "order", "name", "nat_type", "enabled", "description"),
        filters={
            "keyword": Filter(("name", "description")),
            "device": Filter(("device__hostname",)),
            "nat_type": Filter(("nat_type",), "exact"),
            "enabled": Filter(("enabled",), "exact"),
        },
        search=("name",),
        scoped=True,
        # 唯一键是 设备+规则顺序，name 不唯一
        gettable=False,
        select_related=("device", "translated_source", "translated_destination", "translated_service"),
        prefetch=("source_addresses", "destination_addresses", "services"),
        order=("device__hostname", "order"),
    ),
}
