"""MCP 实体注册表（通用层，不属于任何业务域）。

各域把「可被 MCP 查询的模型或视图」登记到这里，通用工具（``core.mcp.tools``）
只认注册表，不认具体域：

- ``register_entity(spec)``：登记一个实体类型（模型或视图 + 序列化器 + 业务键 +
  过滤/排序白名单）；
- ``register_edge(edge)``：登记两个类型之间的有向边（两端必须已登记）。

**本模块不 import 任何域模块**（``assets`` / ``analysis`` / ``docs`` …），也不
import ``core`` 的业务模块（``core.models`` / ``core.api``）——即使物理上放在
``apps/core/mcp/``，它只提供查询基建，不读用户、任务等 core 业务数据。

约定：

- 摘要字段名必须是序列化器里存在的键（``to_dict`` 用 ``.get`` 取，漏写只会少
  一个字段，不会抛异常）；
- 过滤走 ``Filter`` 白名单，不接受任意 ``__`` 查找；
- 边的两端必须先注册，``reverse`` 一定要给（影响面查询全靠反向边）。
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from django.core.exceptions import FieldDoesNotExist
from django.db.models import IntegerField, Q, QuerySet
from mcp.server.mcpserver.exceptions import ToolError

#: 单页上限；超过这个数 LLM 也读不完，只是烧 token
MAX_PAGE_SIZE = 100
#: 关系遍历的最大跳数（防在网状图里绕路）
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

    ``model`` 与 ``queryset_provider`` 二选一：

    - 注册**模型**时给 ``model``（路径校验走 ``_meta``）；
    - 注册**视图**（聚合、跨表、外部结果表）时给 ``queryset_provider``，
      ``model`` 留空，路径校验只能依赖白名单。

    ``scoped=True`` 表示业务键只在单台设备内唯一（``ConfigBase`` 子类），
    ``get_record`` 必须带 ``device`` 限定。
    """

    node_type: str
    label: str
    serializer: type
    key: str
    summary: tuple[str, ...]
    model: type | None = None
    filters: dict[str, Filter] = field(default_factory=dict)
    search: tuple[str, ...] = ()
    scoped: bool = False
    #: False 表示业务键不唯一（如 ARP 表按 设备+IP+MAC 唯一），不能直接 get
    gettable: bool = True
    select_related: tuple[str, ...] = ()
    prefetch: tuple[str, ...] = ()
    order: tuple[str, ...] = ()
    #: 视图注册：没有 model 时用它提供 queryset（每次调用重新取，避免缓存陈旧）
    queryset_provider: Callable[[], QuerySet] | None = None
    #: 域自定义的额外搜索条件（如 MAC 三种分隔符归一），返回 Q 列表
    extra_search: Callable[[str], list[Q]] | None = None
    #: ``bundle`` 不带 sections 时的默认段（留空表示全部可用段）
    default_sections: tuple[str, ...] = ()
    #: 权限钩子：接上用户身份后由这里返回「按 request 过滤」的 queryset；
    #: 内网可信部署保持 None，编译器退回全库（权限永远不来自调用方输入）。
    base_queryset: Callable[[Any], QuerySet] | None = None

    def queryset(self, base: QuerySet | None = None) -> QuerySet:
        if base is not None:
            qs = base
        elif self.queryset_provider is not None:
            qs = self.queryset_provider()
        elif self.model is not None:
            qs = self.model.objects.all()
        else:  # pragma: no cover - 注册时校验，正常不会走到
            raise ToolError(f"{self.node_type} 既没有 model 也没有 queryset_provider，无法查询")
        if self.select_related:
            qs = qs.select_related(*self.select_related)
        if self.prefetch:
            qs = qs.prefetch_related(*self.prefetch)
        if self.order:
            qs = qs.order_by(*self.order)
        return qs


#: 已注册实体（node_type → spec）；由各域在 import 时填充
SPEC: dict[str, EntitySpec] = {}


@dataclass(frozen=True)
class Edge:
    """一条有向边。

    ``forward`` 与 ``reverse`` 都返回**对象可迭代**，用显式 queryset 而不是 Django
    的反向访问器——访问器名由模型类名推导，改名即断。
    """

    name: str
    src: str
    dst: str
    forward: Callable[[Any], Iterable[Any]]
    reverse: Callable[[Any], Iterable[Any]]


#: 已注册的边；由各域在 import 时填充
EDGES: list[Edge] = []


def register_entity(spec: EntitySpec, *, override: bool = False) -> EntitySpec:
    """登记一个实体类型。重复登记默认报错——两个域抢同一个 node_type 通常是笔误。"""
    if not spec.node_type or not spec.node_type.strip():
        raise ValueError("EntitySpec.node_type 不能为空")
    if spec.model is None and spec.queryset_provider is None:
        raise ValueError(f"{spec.node_type} 必须提供 model 或 queryset_provider")
    if spec.node_type in SPEC and not override:
        raise ValueError(f"实体类型已注册：{spec.node_type}（确实要覆盖请传 override=True）")
    SPEC[spec.node_type] = spec
    return spec


def unregister_entity(node_type: str) -> None:
    """注销实体并清理挂在它上面的边（主要用于测试与热替换）。"""
    SPEC.pop(node_type, None)
    EDGES[:] = [edge for edge in EDGES if edge.src != node_type and edge.dst != node_type]


def clear_registry() -> None:
    """清空注册表（测试隔离用；业务代码不要调用）。"""
    SPEC.clear()
    EDGES.clear()


def register_edge(edge: Edge, *, override: bool = False) -> Edge:
    """登记一条边；两端必须先注册，否则报错（避免悬空边在遍历时 KeyError）。"""
    missing = [name for name in (edge.src, edge.dst) if name not in SPEC]
    if missing:
        raise ValueError(f"边 {edge.name} 的端点未注册：{', '.join(missing)}；请先 register_entity")
    duplicate = any(e.name == edge.name and e.src == edge.src and e.dst == edge.dst for e in EDGES)
    if duplicate and not override:
        raise ValueError(f"边已注册：{edge.src} -[{edge.name}]-> {edge.dst}")
    if not duplicate:
        EDGES.append(edge)
    return edge


def get_spec(node_type: str) -> EntitySpec:
    """取实体描述；类型不存在时把**可用类型**回给调用方（LLM 的纠正信号）。"""
    spec = SPEC.get((node_type or "").strip())
    if spec is None:
        options = " / ".join(sorted(SPEC)) or "(尚未注册任何实体)"
        raise ToolError(f"未知的 entity_type：{node_type or '(空)'}；可选值 {options}")
    return spec


def parse_filters(spec: EntitySpec, raw: dict[str, Any] | None) -> list[tuple[str, Any]]:
    """校验并归一化过滤参数，返回 ``[(名字, 值)]``；未声明的键报错而不是忽略。"""
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


def summary_fields(spec: EntitySpec) -> tuple[str, ...]:
    """摘要字段：id + 业务键 + 声明字段，去重保序。"""
    return tuple(dict.fromkeys(("id", spec.key, *spec.summary)))


def to_dict(spec: EntitySpec, obj: Any, *, full: bool = False) -> dict[str, Any]:
    """按序列化器口径输出；``full=False`` 只留摘要（列表层给全字段是 token 浪费）。"""
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


def business_key_q(spec: EntitySpec, text: str) -> Q | None:
    """业务键的查询条件：数字键（VLAN 的 ``vid``）必须走 exact 交给字段转 int。

    ``vid__iexact`` 在 PostgreSQL 上会变成对整数列做 ``UPPER()``，直接报 SQL 错误；
    而纯数字又可能是主键，所以键的类型必须由模型字段决定，不能一律按文本比。
    """
    if spec.model is not None:
        try:
            field = spec.model._meta.get_field(spec.key)
        except FieldDoesNotExist:  # pragma: no cover - spec 写错时由 query 层的路径校验兜住
            field = None
        if isinstance(field, IntegerField):
            return Q(**{spec.key: text}) if text.isdigit() else None
    return Q(**{f"{spec.key}__iexact": text})


def resolve_one(spec: EntitySpec, key: str, device: str = "") -> Any:
    """按业务键取单条（scoped 类型必须给 device）。

    **业务键优先于主键**：数字业务键（VLAN 的 vid）不能被同号主键抢走——``key="1"``
    曾经在「vid=7 的记录恰好 pk=1」时返回错的那条。只有业务键查不到时才把纯数字
    当 id 兜底（方便从其它工具返回的 id 直接跳过来）。
    """
    text = (key or "").strip()
    if not text:
        raise ToolError(f"{spec.node_type} 的 key 不能为空（业务键是 {spec.key}）")
    qs = spec.queryset()
    if spec.scoped:
        if not device:
            raise ToolError(f"{spec.node_type} 需要 device 参数（主机名）限定：{spec.key} 只在单台设备内唯一")
        qs = qs.filter(device__hostname__iexact=device.strip())
    # gettable=False 的实体业务键不唯一（arp_mac 是 设备+IP+MAC），按 key 取只能随便给一条
    cond = business_key_q(spec, text) if spec.gettable else None
    if cond is not None:
        hit = qs.filter(cond).first()
        if hit is not None:
            return hit
    if text.isdigit():
        hit = qs.filter(pk=int(text)).first()
        if hit is not None:
            return hit
    if not spec.gettable:
        raise ToolError(
            f"{spec.label}不能按 {spec.key} 直接取：它不唯一（真实键是 设备+{spec.key}+更多字段）。"
            f"请用 list_records(entity_type='{spec.node_type}', filters=...)、locate，或传数字主键 id"
        )
    options = " / ".join(sorted(spec.filters)) or "(无)"
    raise ToolError(f"{spec.label}不存在：{text}；{spec.key} 需精确匹配，可先用 find 定位，或用 list_records(entity_type='{spec.node_type}') 按 {options} 过滤")


def edges_from(node_type: str) -> list[Edge]:
    return [edge for edge in EDGES if edge.src == node_type]


def edges_to(node_type: str) -> list[Edge]:
    return [edge for edge in EDGES if edge.dst == node_type]


def edge_named(node_type: str, name: str) -> Edge:
    """取某个类型上名为 ``name`` 的正向边（``get_record`` 的 include 用）。"""
    for edge in edges_from(node_type):
        if edge.name == name:
            return edge
    options = " / ".join(sorted({edge.name for edge in edges_from(node_type)}))
    raise ToolError(f"{node_type} 不支持 include：{name}；可选值 {options or '(无)'}")


def edge_options(node_type: str) -> list[str]:
    return sorted({edge.name for edge in edges_from(node_type)})


__all__ = [
    "EDGES",
    "MAX_DEPTH",
    "MAX_PAGE_SIZE",
    "SPEC",
    "Edge",
    "EntitySpec",
    "Filter",
    "apply_filters",
    "business_key_q",
    "clear_registry",
    "edge_named",
    "edge_options",
    "edges_from",
    "edges_to",
    "get_spec",
    "key_value",
    "parse_filters",
    "register_edge",
    "register_entity",
    "resolve_one",
    "summary_fields",
    "to_dict",
    "unregister_entity",
]
