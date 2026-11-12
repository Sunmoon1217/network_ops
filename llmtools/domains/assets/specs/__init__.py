"""资产域的 MCP 实体声明入口（由 ``llmtools.domains.assets.register()`` 触发）。

**布局**（实体按子域分文件，边独立一层）：

| 文件 | 内容 |
|------|------|
| ``../nodes.py`` | ``NodeType``，零 import 的公共词汇表 |
| ``../edges.py`` | 36 条关系边（不属于任何子域） |
| ``ipam.py`` | 设备 / 设备组 / 接口 / VLAN / VRF / 路由 / 子网 / IP / ARP |
| ``slb.py`` | LTM / GTM 全部表 |
| ``firewall.py`` | 地址簿 / 服务簿 / 安全策略 / NAT 规则 |
| ``owners.py`` | 服务器负责人（唯一没有 device 外键的表） |
| ``_helpers.py`` | MAC 归一化（``arp_mac`` 的 ``extra_search`` 与 ``locate`` 共用） |

新增一张表：在对应子域的 ``BUNDLE`` 里加一条 spec，需要挂到图上就在 ``../edges.py``
加边；工具层零改动。

**三条约束**（改任何 spec 前先读）：

- **摘要字段名必须是序列化器里存在的键**。字段口径复用 ``assets.serializers``
  （与 REST API 同一套），不在工具层另造字段名；漏写只是少一个字段
  （``to_dict`` 用 ``.get`` 取），不会抛异常，但会静默丢信息。
- **过滤操作符走白名单**。``list_records`` 不接受任意 ``__`` 查找。
- **边的两端必须是已登记类型，且 ``reverse`` 一定要给**。影响面查询全靠反向边。

**为什么入口要跑校验**：拆成多个文件后，「``node_type`` 不撞名」「同一个 ``src`` 下
边名唯一」这两条不变量不再肉眼可见，所以这里在 import 期就炸，而不是等 LLM 调出
一个串台的结果。
"""

from llmtools.registry import EDGES, SPEC, Edge, EntitySpec, register_edge, register_entity

from ..edges import EDGES as DOMAIN_EDGES
from ..nodes import NodeType
from . import firewall, ipam, owners, slb

#: 合并顺序 = 原先单文件里的声明顺序（``SPEC`` 的插入顺序会进错误提示与返回结果）
_SUBDOMAINS = (ipam, slb, firewall, owners)


def _merge_entities() -> dict[str, EntitySpec]:
    bundle: dict[str, EntitySpec] = {}
    for module in _SUBDOMAINS:
        for node_type, spec in module.BUNDLE.items():
            if node_type in bundle:
                raise ValueError(f"实体类型 {node_type} 在多个子域重复声明（{module.__name__}）")
            if spec.node_type != node_type:
                raise ValueError(f"{module.__name__}：键 {node_type} 与 spec.node_type={spec.node_type} 不一致")
            bundle[node_type] = spec
    return bundle


_BUNDLE: dict[str, EntitySpec] = _merge_entities()


def _validate_edges() -> None:
    """端点必须已声明；同一个 ``src`` 下边名必须唯一（``edge_named`` 只取第一条命中）。"""
    seen: dict[tuple[str, str], Edge] = {}
    for edge in DOMAIN_EDGES:
        for end in (edge.src, edge.dst):
            if end not in _BUNDLE:
                raise ValueError(f"边 {edge.name} 的端点 {end} 未在任何子域声明")
        key = (edge.src, edge.name)
        if key in seen:
            raise ValueError(f"{edge.src} 上有两条同名边 {edge.name}（→ {seen[key].dst} / → {edge.dst}）：edge_named 只取第一条，include=... 会静默串台")
        seen[key] = edge


_validate_edges()


def register() -> None:
    """把本域实体与边登记到 llmtools.registry（由 ``llmtools.domains.assets.register()`` 调用）。

    幂等：已登记的类型与边跳过（``clear_registry()`` 之后重跑也安全）。
    """
    for spec in _BUNDLE.values():
        if spec.node_type not in SPEC:
            register_entity(spec)
    for edge in DOMAIN_EDGES:
        if not any(e.name == edge.name and e.src == edge.src and e.dst == edge.dst for e in EDGES):
            register_edge(edge)


# 刻意**不在**模块底部自动调用：注册由 llmtools/__init__.py 经 assets.register() 显式触发——
# import 一个声明模块不应悄悄改写全局注册表，与工具侧「TOOLS 名单 + register_all()」同一套语义。


__all__ = [
    "EDGES",
    "SPEC",
    "NodeType",
    "register",
]
