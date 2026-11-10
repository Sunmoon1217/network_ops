"""结构化查询计划（MCP 的「受控 ORM」编译入口）。

``list_records`` 的 ``filters`` 是「别名 → 单值」的简单过滤，表达不了 AND/OR、
多字段排序、字段投影与 offset。本模块补这一层：把调用方给的 ``QueryPlan``（纯数据）
编译成经过白名单校验的 ``QuerySet``，**不接受任何 ORM 字符串或任意 ``__`` 查找**。

安全口径与 ``entities.Filter`` 一致，只是把「别名」换成真实字段路径：

- 过滤字段：只允许 ``EntitySpec.filters`` 里声明过的路径（含多跳，如
  ``device_model__vendor__name``）与业务键；
- 排序字段：只允许 ``EntitySpec.order``、业务键与 ``id``；
- 投影字段：默认摘要，``fields=["*"]`` 才给全字段；
- 操作符：``exact/iexact/icontains/istartswith/gte/lte/in/isnull``。

路径仍逐段过 ``_meta.get_field``：spec 写错时在编译期就报错，而不是把
``FieldError`` 抛给调用方。

**权限钩子**：``EntitySpec.base_queryset`` 为空时按全库查询（当前内网可信部署）。
将来给 MCP 接上用户身份后，只需在 spec 上挂一个「按 request 过滤」的函数，编译器
会以它为起点——权限条件永远不来自调用方输入。
"""

from dataclasses import dataclass
from typing import Any, Literal

from django.core.exceptions import FieldDoesNotExist
from django.db.models import Q, QuerySet
from mcp.server.mcpserver.exceptions import ToolError

from core.mcp.registry import MAX_PAGE_SIZE, EntitySpec, get_spec, summary_fields, to_dict

#: 过滤操作符白名单（与 ``entities.Filter`` 保持一致，不开放任意 lookup）
OPERATORS = ("exact", "iexact", "icontains", "istartswith", "gte", "lte", "in", "isnull")

PLAN_KEYS = frozenset({"entity_type", "filters", "logic", "order_by", "fields", "limit", "offset"})
FILTER_KEYS = frozenset({"field", "op", "value"})
ORDER_KEYS = frozenset({"field", "direction"})

DEFAULT_LIMIT = 20


@dataclass(frozen=True)
class FilterSpec:
    field: str
    op: str = "exact"
    value: Any = None


@dataclass(frozen=True)
class OrderSpec:
    field: str
    direction: Literal["asc", "desc"] = "asc"


@dataclass(frozen=True)
class QueryPlan:
    entity_type: str
    filters: tuple[FilterSpec, ...] = ()
    logic: Literal["and", "or"] = "and"
    order_by: tuple[OrderSpec, ...] = ()
    #: None → 摘要字段；``["*"]`` → 全字段；否则只给指定列
    fields: tuple[str, ...] | None = None
    limit: int = DEFAULT_LIMIT
    offset: int = 0


# ---------------------------------------------------------------------------
# 白名单
# ---------------------------------------------------------------------------


def _filter_fields(spec: EntitySpec) -> set[str]:
    """可用于过滤的真实字段路径：spec 里声明过的路径 + 业务键。"""
    fields = {spec.key}
    for item in spec.filters.values():
        fields.update(item.fields)
    return fields


def _order_fields(spec: EntitySpec) -> set[str]:
    return {spec.key, "id", *spec.order}


def _options(values: set[str] | tuple[str, ...]) -> str:
    return " / ".join(sorted(values)) or "(无)"


def _walk_field_path(model: type | None, path: str) -> None:
    """逐段确认路径在 ``_meta`` 中真实存在；视图注册没有 model，只能依赖白名单。"""
    if model is None:
        return
    current = model
    for segment in path.split("__"):
        try:
            current_field = current._meta.get_field(segment)
        except FieldDoesNotExist as exc:
            raise ToolError(f"字段路径 {path} 中的 {segment} 不存在") from exc
        if current_field.is_relation:
            current = current_field.related_model


def _check_filter_field(spec: EntitySpec, name: str) -> None:
    allowed = _filter_fields(spec)
    if name not in allowed:
        raise ToolError(f"{spec.node_type} 不支持按 {name} 过滤；可选路径 {_options(allowed)}")
    _walk_field_path(spec.model, name)


def _check_order_field(spec: EntitySpec, name: str) -> None:
    allowed = _order_fields(spec)
    if name not in allowed:
        raise ToolError(f"{spec.node_type} 不支持按 {name} 排序；可选字段 {_options(allowed)}")
    _walk_field_path(spec.model, name)


def _check_projection(spec: EntitySpec, fields: tuple[str, ...] | None) -> None:
    if fields is None or fields == ("*",):
        return
    allowed = set(summary_fields(spec))
    unknown = [name for name in fields if name not in allowed]
    if unknown:
        raise ToolError(
            f"{spec.node_type} 不能投影字段 {', '.join(unknown)}；可选字段 {_options(allowed)}，"
            '要全字段请传 fields=["*"]'
        )


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------


def _filter_spec(raw: Any, index: int) -> FilterSpec:
    if not isinstance(raw, dict):
        raise ToolError(f"filters[{index}] 必须是对象，如 {{'field': 'hostname', 'op': 'icontains', 'value': 'NET'}}")
    unknown = sorted(set(raw) - FILTER_KEYS)
    if unknown:
        raise ToolError(f"filters[{index}] 出现未声明字段：{', '.join(unknown)}；只允许 {_options(FILTER_KEYS)}")
    name = str(raw.get("field") or "").strip()
    if not name:
        raise ToolError(f"filters[{index}] 缺少 field")
    op = str(raw.get("op") or "exact").strip()
    if op not in OPERATORS:
        raise ToolError(f"filters[{index}] 不支持操作符 {op}；可选值 {_options(OPERATORS)}")
    return FilterSpec(field=name, op=op, value=raw.get("value"))


def _order_spec(raw: Any, index: int) -> OrderSpec:
    if not isinstance(raw, dict):
        raise ToolError(f"order_by[{index}] 必须是对象，如 {{'field': 'hostname', 'direction': 'asc'}}")
    unknown = sorted(set(raw) - ORDER_KEYS)
    if unknown:
        raise ToolError(f"order_by[{index}] 出现未声明字段：{', '.join(unknown)}；只允许 {_options(ORDER_KEYS)}")
    name = str(raw.get("field") or "").strip()
    if not name:
        raise ToolError(f"order_by[{index}] 缺少 field")
    direction = str(raw.get("direction") or "asc").strip()
    if direction not in {"asc", "desc"}:
        raise ToolError(f"order_by[{index}] 的 direction 取 asc / desc")
    return OrderSpec(field=name, direction=direction)


def parse_plan(spec: EntitySpec, raw: dict[str, Any]) -> QueryPlan:
    """校验并归一化调用方给的 plan；任何未声明的键/字段/操作符都报错。"""
    if not isinstance(raw, dict):
        raise ToolError("plan 必须是对象，见 query 工具的字段说明")
    unknown = sorted(set(raw) - PLAN_KEYS)
    if unknown:
        raise ToolError(f"plan 出现未声明字段：{', '.join(unknown)}；只允许 {_options(PLAN_KEYS)}")

    logic = str(raw.get("logic") or "and").strip()
    if logic not in {"and", "or"}:
        raise ToolError("plan.logic 取 and / or")

    raw_filters = raw.get("filters") or []
    if not isinstance(raw_filters, list):
        raise ToolError("plan.filters 必须是数组")
    filters = tuple(_filter_spec(item, index) for index, item in enumerate(raw_filters))
    for item in filters:
        _check_filter_field(spec, item.field)

    raw_order = raw.get("order_by") or []
    if not isinstance(raw_order, list):
        raise ToolError("plan.order_by 必须是数组")
    order_by = tuple(_order_spec(item, index) for index, item in enumerate(raw_order))
    for item in order_by:
        _check_order_field(spec, item.field)

    raw_fields = raw.get("fields")
    fields: tuple[str, ...] | None = None
    if raw_fields is not None:
        if not isinstance(raw_fields, list) or not raw_fields:
            raise ToolError('plan.fields 必须是字段数组；不要投影就省略，要全字段传 ["*"]')
        fields = tuple(str(name).strip() for name in raw_fields)
        _check_projection(spec, fields)

    limit = raw.get("limit", DEFAULT_LIMIT)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_PAGE_SIZE:
        raise ToolError(f"plan.limit 取 1~{MAX_PAGE_SIZE}")

    offset = raw.get("offset", 0)
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise ToolError("plan.offset 取 >= 0 的整数")

    return QueryPlan(
        entity_type=spec.node_type,
        filters=filters,
        logic=logic,
        order_by=order_by,
        fields=fields,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# 编译
# ---------------------------------------------------------------------------


def _lookup_q(item: FilterSpec) -> Q:
    if item.op == "in":
        if not isinstance(item.value, (list, tuple)) or not item.value:
            raise ToolError(f"{item.field} 的 in 需要非空数组")
        value: Any = list(item.value)
    elif item.op == "isnull":
        if not isinstance(item.value, bool):
            raise ToolError(f"{item.field} 的 isnull 需要 true / false")
        value = item.value
    else:
        if item.value in (None, "", []):
            raise ToolError(f"{item.field} 的 {item.op} 需要非空值")
        value = item.value
    lookup = item.field if item.op == "exact" else f"{item.field}__{item.op}"
    return Q(**{lookup: value})


def compile_plan(plan: QueryPlan, *, spec: EntitySpec | None = None, request: Any = None) -> QuerySet:
    """把 plan 编译成 QuerySet。

    权限起点来自 ``spec.base_queryset``（而不是 plan）；当前内网可信部署它为 None，
    等于全库。排序/limit/offset 由调用方决定，这里只负责过滤与排序。
    """
    spec = spec or get_spec(plan.entity_type)
    base = spec.base_queryset(request) if (spec.base_queryset is not None and request is not None) else None
    qs = spec.queryset(base)

    if plan.filters:
        cond = Q()
        for item in plan.filters:
            cond = (cond & _lookup_q(item)) if plan.logic == "and" else (cond | _lookup_q(item))
        # 过滤路径可能穿过 to-many（group_memberships），必须去重
        qs = qs.filter(cond).distinct()

    if plan.order_by:
        qs = qs.order_by(*[("-" if item.direction == "desc" else "") + item.field for item in plan.order_by])
    return qs


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------


def project(spec: EntitySpec, obj: Any, fields: tuple[str, ...] | None) -> dict[str, Any]:
    """按 plan.fields 投影；``None`` 走摘要，``("*",)`` 走全字段。"""
    if fields == ("*",):
        return to_dict(spec, obj, full=True)
    if fields:
        data = to_dict(spec, obj, full=True)
        return {name: data.get(name) for name in fields}
    return to_dict(spec, obj)


def plan_summary(plan: QueryPlan) -> dict[str, Any]:
    """归一化后的 plan 回显：让调用方确认编译器实际理解了什么。"""
    return {
        "entity_type": plan.entity_type,
        "filters": [{"field": item.field, "op": item.op, "value": item.value} for item in plan.filters],
        "logic": plan.logic,
        "order_by": [{"field": item.field, "direction": item.direction} for item in plan.order_by],
        "fields": list(plan.fields) if plan.fields is not None else None,
        "limit": plan.limit,
        "offset": plan.offset,
    }


__all__ = [
    "OPERATORS",
    "FilterSpec",
    "OrderSpec",
    "QueryPlan",
    "compile_plan",
    "parse_plan",
    "plan_summary",
    "project",
]
