"""统一配置项与软资产（T1 / T4）：物理机 / 虚拟机 / 数据库实例 / 应用服务 / 域名 / LB 服务。

业务键的取舍：

- ``DomainAsset.fqdn`` / ``LoadBalancerService.asset_key`` 是**归并生成的唯一键**，直接当 key；
- 四张 ``_CIExtension`` 扩展表的 ``hostname`` **不唯一**（还可能为空），所以 key 用扩展表
  自增 ``id``，同时把 ``ci_id`` / ``ci_name` 放进摘要——跨类型引用一律以 CI 标识为准
  （``ci_id`` 在序列化器里有声明字段，``summary`` 不会静默丢）；
- ``ci_id`` 过滤走 ``ci__ci_id`` 跨表路径（``Filter`` 白名单允许，``apply_filters`` 会
  ``distinct``），LLM 可以从 ``configuration_item`` 的结果直接跳到对应扩展表。

这六类都是**人工台账 / 归并产物**，不是 ``ConfigBase`` 配置行：没有 ``device`` 外键，
所以 ``scoped=False``；写入侧（REST CRUD / 归并链路）与本工具无关，MCP 只做查询。
"""

from assets import models
from assets.serializers import views as s
from llmtools.registry import EntitySpec, Filter

from ..nodes import NodeType

BUNDLE: dict[str, EntitySpec] = {
    # —— T1：四类 CI 扩展（人工录入的台账，key 用扩展表 id）——
    NodeType.PHYSICAL_SERVER: EntitySpec(
        node_type=NodeType.PHYSICAL_SERVER,
        label="物理机",
        model=models.PhysicalServer,
        serializer=s.PhysicalServerSerializer,
        key="id",
        summary=("ci_id", "ci_name", "hostname", "mgmt_ip", "os", "serial_number"),
        filters={
            "keyword": Filter(("hostname", "mgmt_ip", "serial_number")),
            "ci_id": Filter(("ci__ci_id",), "exact"),
        },
        search=("hostname", "mgmt_ip"),
        order=("hostname",),
    ),
    NodeType.VIRTUAL_MACHINE: EntitySpec(
        node_type=NodeType.VIRTUAL_MACHINE,
        label="虚拟机",
        model=models.VirtualMachine,
        serializer=s.VirtualMachineSerializer,
        key="id",
        summary=("ci_id", "ci_name", "hostname", "host_name", "mgmt_ip", "os"),
        filters={
            "keyword": Filter(("hostname", "host_name", "mgmt_ip")),
            "ci_id": Filter(("ci__ci_id",), "exact"),
        },
        search=("hostname", "mgmt_ip"),
        order=("hostname",),
    ),
    NodeType.DATABASE_INSTANCE: EntitySpec(
        node_type=NodeType.DATABASE_INSTANCE,
        label="数据库实例",
        model=models.DatabaseInstance,
        serializer=s.DatabaseInstanceSerializer,
        key="id",
        summary=("ci_id", "ci_name", "engine", "version", "port", "host_name"),
        filters={
            "keyword": Filter(("engine", "version", "host_name")),
            "ci_id": Filter(("ci__ci_id",), "exact"),
        },
        search=("engine", "host_name"),
        order=("engine", "ci__name"),
    ),
    NodeType.APPLICATION_SERVICE: EntitySpec(
        node_type=NodeType.APPLICATION_SERVICE,
        label="应用服务",
        model=models.ApplicationService,
        serializer=s.ApplicationServiceSerializer,
        key="id",
        summary=("ci_id", "ci_name", "service_type", "port", "url_path"),
        filters={
            "keyword": Filter(("service_type", "url_path")),
            "ci_id": Filter(("ci__ci_id",), "exact"),
        },
        search=("service_type", "url_path"),
        order=("service_type", "ci__name"),
    ),
    # —— T4：软资产（归并产物，key 用归一键）——
    NodeType.DOMAIN: EntitySpec(
        node_type=NodeType.DOMAIN,
        label="域名资产",
        model=models.DomainAsset,
        serializer=s.DomainAssetSerializer,
        key="fqdn",
        summary=("fqdn", "ci_id", "rtypes", "ttl", "lb_mode", "devices", "inconsistent"),
        filters={
            "keyword": Filter(("fqdn",)),
            "lb_mode": Filter(("lb_mode",)),
        },
        search=("fqdn",),
        order=("fqdn",),
    ),
    NodeType.LOAD_BALANCER_SERVICE: EntitySpec(
        node_type=NodeType.LOAD_BALANCER_SERVICE,
        label="负载均衡服务",
        model=models.LoadBalancerService,
        serializer=s.LoadBalancerServiceSerializer,
        key="asset_key",
        summary=("asset_key", "ci_id", "vip", "port", "protocol", "member_count", "status", "devices", "inconsistent"),
        filters={
            "keyword": Filter(("asset_key", "vip")),
            "port": Filter(("port",), "exact"),
            "status": Filter(("status",)),
        },
        search=("asset_key", "vip"),
        order=("vip", "port"),
    ),
}
