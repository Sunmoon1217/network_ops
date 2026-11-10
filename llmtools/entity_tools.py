"""MCP 通用实体工具（LLM 出口）。

本模块只认 ``llmtools.registry``，不 import 任何域模块。工具函数是**纯函数**、不加
``@mcp.tool()``：注册在 ``llmtools/tools.py``（名单 + 包装 + 重名校验），所以能被单测直调。

「什么情况下才新开一个工具」与列表/详情/错误串的三条返回纪律见 docs/llmtools.md
"""

import ipaddress
import re
from typing import Any

from django.db.models import Q, QuerySet
from mcp.server.mcpserver.exceptions import ToolError

from llmtools.query import compile_plan, parse_plan, plan_summary, project
from llmtools.registry import (
    MAX_DEPTH,
    MAX_PAGE_SIZE,
    SPEC,
    apply_filters,
    edge_named,
    edge_options,
    edges_from,
    edges_to,
    get_spec,
    key_value,
    parse_filters,
    resolve_one,
    to_dict,
)

#: 单次关系展开 / 片段的返回条数上限：再多 LLM 也读不完，只是烧 token
MAX_ROWS = 50


# 通用小工具


def _page_slice(page: int, page_size: int) -> tuple[int, int]:
    if page < 1:
        raise ToolError("page 从 1 开始计数")
    if not 1 <= page_size <= MAX_PAGE_SIZE:
        raise ToolError(f"page_size 取 1~{MAX_PAGE_SIZE}")
    start = (page - 1) * page_size
    return start, start + page_size


def _parse_types(types: str) -> list[str]:
    """``"device,subnet"`` → 校验过的类型列表（未知类型在这里就报错）。"""
    items = [item.strip() for item in (types or "").split(",") if item.strip()]
    for item in items:
        get_spec(item)
    return items


def _mac_compact(text: str) -> str:
    """去掉分隔符后的 12 位小写十六进制；不是 MAC 形态返回空串。

    ARP 表里 MAC 存的是原始串，三种写法（``aa-bb-cc-dd-ee-ff`` / ``aabb.ccdd.eeff``
    / ``AA:BB:CC``）都出现过。不先归一化，MAC 查询十次有九次查不到——这是这类
    工具最典型的失败原因。
    """
    compact = re.sub(r"[^0-9a-fA-F]", "", text or "").lower()
    return compact if len(compact) == 12 else ""


def _parse_ip(text: str) -> str:
    """能当单个地址就返回规范串（顺带抹平 IPv6 压缩写法差异），否则空串。"""
    try:
        return str(ipaddress.ip_address(text.strip()))
    except ValueError:
        return ""


def _parse_network(text: str) -> str:
    try:
        return str(ipaddress.ip_network(text.strip(), strict=False))
    except ValueError:
        return ""


def _detect(text: str) -> str:
    """输入形态判别：mac / ip / net / text。"""
    if _mac_compact(text):
        return "mac"
    if _parse_ip(text):
        return "ip"
    if "/" in text and _parse_network(text):
        return "net"
    return "text"


def _score(value: str, text: str) -> int:
    low, needle = (value or "").lower(), text.lower()
    if low == needle:
        return 3
    if low.startswith(needle):
        return 2
    return 1 if needle in low else 0


def _rows(spec, objs, *, full: bool = False, cap: int = MAX_ROWS) -> tuple[list[dict], int]:
    """序列化一批对象，返回 ``(行, 总条数)``。

    queryset 走 ``count()`` + 切片，不把全表拉进内存；list 直接算长度。
    """
    if isinstance(objs, QuerySet):
        total = objs.count()
        items = list(objs[:cap])
    else:
        items = list(objs)
        total = len(items)
        items = items[:cap]
    return [to_dict(spec, obj, full=full) for obj in items], total


# find：跨类型定位


def find(q: str, types: str = "", limit: int = 10) -> dict[str, Any]:
    """跨实体类型定位：给一个字符串，找出它可能是谁（主机名 / IP / MAC / 域名 / 网段）。

    典型用法：「10.0.1.5 是谁」「pay-gw 在哪」「这个域名挂在哪个设备上」。
    **返回多类型候选而不是替调用方挑一个**——同一个串可以既是 IP 又命中某台设备的
    备注片段，判断权留给调用方；下一步用 get_record / locate 消歧。

    参数：
    - q：查询串，必填
    - types：逗号分隔的类型白名单（如 "device,ip_address"），留空查全部可搜类型
    - limit：候选条数上限，1~30

    返回：{query, hint, total, returned, truncated, candidates:[{entity_type, label,
    key, score, summary}]}。score 3=完全相等 / 2=前缀匹配 / 1=包含，按 score 降序。
    """
    text = (q or "").strip()
    if not text:
        raise ToolError("q 不能为空：可传主机名 / IP / MAC / 域名 / 网段")
    if not 1 <= limit <= 30:
        raise ToolError("limit 取 1~30")

    hint = _detect(text)
    wanted = _parse_types(types) if types else [node_type for node_type, spec in SPEC.items() if spec.search]

    hits: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for node_type in wanted:
        spec = SPEC[node_type]
        if not spec.search:
            continue
        cond = Q()
        for field in spec.search:
            cond |= Q(**{f"{field}__icontains": text})
        # 域自定义的额外条件（如 MAC 三种分隔符归一），由 spec 提供
        if spec.extra_search:
            for extra in spec.extra_search(text):
                cond |= extra
        for obj in spec.queryset().filter(cond)[:3]:
            if (node_type, obj.pk) in seen:
                continue
            seen.add((node_type, obj.pk))
            values = [str(getattr(obj, field, "") or "") for field in (*spec.search, spec.key)]
            hits.append(
                {
                    "entity_type": node_type,
                    "label": spec.label,
                    "key": key_value(spec, obj),
                    "score": max((_score(value, text) for value in values), default=0),
                    "summary": to_dict(spec, obj),
                }
            )

    hits.sort(key=lambda item: (-item["score"], item["entity_type"], item["key"]))
    return {
        "query": text,
        "hint": hint,
        "total": len(hits),
        "returned": min(len(hits), limit),
        "truncated": len(hits) > limit,
        "candidates": hits[:limit],
    }


# list_records：通用列表


def list_records(
    entity_type: str,
    filters: dict[str, Any] | None = None,
    page: int = 1,
    page_size: int = 20,
    detail: bool = False,
    order: str = "",
) -> dict[str, Any]:
    """按类型分页列出实体，替代「每张表一个 list 工具」的做法。

    参数：
    - entity_type：实体类型（device / interface / route / ip_address / arp_mac / ...）
    - filters：字段过滤，键必须在该类型声明的白名单内；常用键：keyword（模糊匹配多个
      字段）、device（设备主机名）、status、vlan、subnet。未声明的键会**报错而不是
      被忽略**——静默忽略会让调用方以为过滤生效了，从而给出范围过宽的结论
    - detail：False 返回摘要字段，True 返回序列化器全字段
    - order：排序字段，必须是该类型声明的排序项（留空用默认排序）

    返回：{entity_type, total, page, page_size, returned, truncated, rows}。
    **务必看 total**：它才是匹配总数，rows 只是当前页。
    """
    spec = get_spec(entity_type)
    start, stop = _page_slice(page, page_size)
    if order and order not in spec.order:
        options = " / ".join(spec.order) or "(无)"
        raise ToolError(f"{entity_type} 不支持按 {order} 排序；可选值 {options}")

    qs = spec.queryset()
    # spec.queryset() 贴的是声明里的默认排序；调用方指定的 order 必须显式覆盖，
    # 否则「校验通过但没生效」——静默给出错误顺序比报错更坑
    if order:
        qs = qs.order_by(order)
    qs, _ = apply_filters(spec, qs, parse_filters(spec, filters))
    total = qs.count()
    rows = [to_dict(spec, obj, full=detail) for obj in qs[start:stop]]
    return {
        "entity_type": entity_type,
        "total": total,
        "page": page,
        "page_size": page_size,
        "returned": len(rows),
        "truncated": start + len(rows) < total,
        "rows": rows,
    }


# query：结构化查询计划


def query(plan: dict[str, Any]) -> dict[str, Any]:
    """结构化查询：用 QueryPlan 表达 AND/OR、多字段排序、字段投影与 offset。

    与 ``list_records`` 的分工：单条件、按别名过滤用 ``list_records``；需要组合条件、
    多字段排序或只取几列时用本工具。``plan`` 里的字段路径与操作符都在白名单内，
    未声明的键会报错而不是被静默忽略。

    plan 结构：
    - entity_type：实体类型（同 list_records）
    - filters：[{field, op, value}]，field 用**真实字段路径**（如 device_model__vendor__name、
      device__hostname），op 取 exact / iexact / icontains / istartswith / gte / lte / in / isnull
    - logic：and / or（filters 之间的组合方式，默认 and）
    - order_by：[{field, direction}]，direction 取 asc / desc
    - fields：只返回这些列（默认摘要字段）；``["*"]`` 返回序列化器全字段
    - limit：1~100（默认 20）；offset：>= 0

    返回：{entity_type, total, offset, limit, returned, truncated, plan, rows}。
    和 list_records 一样，**total 才是匹配总数**，rows 只是当前窗口；``plan`` 是
    编译器归一化后的回显，用来确认条件真的生效了。
    """
    if not isinstance(plan, dict):
        raise ToolError("plan 必须是对象，字段见本工具说明")
    spec = get_spec(str(plan.get("entity_type") or "").strip())
    parsed = parse_plan(spec, plan)
    qs = compile_plan(parsed, spec=spec)
    total = qs.count()
    rows = [project(spec, obj, parsed.fields) for obj in qs[parsed.offset : parsed.offset + parsed.limit]]
    return {
        "entity_type": spec.node_type,
        "total": total,
        "offset": parsed.offset,
        "limit": parsed.limit,
        "returned": len(rows),
        "truncated": parsed.offset + len(rows) < total,
        "plan": plan_summary(parsed),
        "rows": rows,
    }


# get_record：单条详情 + 关系展开


def get_record(entity_type: str, key: str, device: str = "", include: str = "") -> dict[str, Any]:
    """按业务键取单条实体的完整档案，可选展开一跳关系。

    参数：
    - entity_type：实体类型
    - key：业务键值。device=主机名、subnet=网段、ip_address=IP、interface=接口名；
      也接受数字主键，方便从别的工具返回的 id 直接跳过来
    - device：**scoped 类型必填**（interface / vlan / vrf / route / ltm_* / gtm_*）。
      每台交换机都有叫 Gi1/0/1 的口，不带设备等于瞎猜
    - include：逗号分隔的关系名（见该类型的可用段，如 "groups,interfaces"），留空不展开

    返回：{entity_type, key, record, relations:{关系名:{entity_type, total, returned,
    truncated, rows}}}。
    """
    spec = get_spec(entity_type)
    obj = resolve_one(spec, key, device)

    relations: dict[str, Any] = {}
    for name in [item.strip() for item in (include or "").split(",") if item.strip()]:
        edge = edge_named(spec.node_type, name)
        dst_spec = SPEC[edge.dst]
        rows, total = _rows(dst_spec, edge.forward(obj))
        relations[name] = {
            "entity_type": edge.dst,
            "total": total,
            "returned": len(rows),
            "truncated": total > len(rows),
            "rows": rows,
        }

    return {
        "entity_type": entity_type,
        "key": key_value(spec, obj),
        "record": to_dict(spec, obj, full=True),
        "relations": relations,
    }


# bundle：一个实体的横切面


def bundle(entity_type: str = "device", key: str = "", sections: str = "", device: str = "") -> dict[str, Any]:
    """一次性取某个实体的「档案 + 若干段关联数据」，省掉连续多次调用。

    「这台设备什么情况」是最高频的问法：先 get_record 拿档案，再分别查接口、IP、ARP、
    设备组，是 4~5 次往返，每次还要重新确认主机名。这里合成一次。

    参数：
    - entity_type：默认 device
    - key：业务键（device 传主机名）
    - sections：逗号分隔的段名；留空取该类型的默认段（device 默认
      "groups,interfaces,ip_addresses,arp"）；传 "all" 取全部可用段
    - device：scoped 类型的设备限定（同 get_record）

    返回：{entity_type, key, profile, sections:{段名:{entity_type, total, returned,
    truncated, rows}}}。每段单独带 total，用它判断有没有被截断。
    """
    spec = get_spec(entity_type)
    obj = resolve_one(spec, key, device)

    available = edge_options(spec.node_type)
    wanted = [name.strip() for name in (sections or "").split(",") if name.strip()]
    if not wanted:
        default = spec.default_sections
        wanted = [name for name in default if name in available] if default else available
    elif wanted == ["all"]:
        wanted = available

    payload: dict[str, Any] = {}
    for name in wanted:
        edge = edge_named(spec.node_type, name)
        dst_spec = SPEC[edge.dst]
        rows, total = _rows(dst_spec, edge.forward(obj))
        payload[name] = {
            "entity_type": edge.dst,
            "total": total,
            "returned": len(rows),
            "truncated": total > len(rows),
            "rows": rows,
        }

    return {
        "entity_type": entity_type,
        "key": key_value(spec, obj),
        "profile": to_dict(spec, obj, full=True),
        "sections": payload,
    }


# relations：变深图遍历


def relations(
    entity_type: str,
    key: str,
    direction: str = "down",
    types: str = "",
    depth: int = 1,
    limit: int = 200,
    device: str = "",
) -> dict[str, Any]:
    """沿实体关系图展开，回答「我下面有什么」和「谁依赖我」。

    方向语义：``down`` 走正向边（设备 → 接口 / IP / ARP / 组），``up`` 走反向边
    （**影响面**：这个地址被哪些设备观测到、这条 ARP 属于哪台设备）。

    参数：
    - direction：down / up / both
    - types：只保留这些类型的节点（逗号分隔），用来砍掉无关分支
    - depth：跳数，1~4。资产树一般 3 层够用，硬上限是防爆
    - limit：节点总数上限，1~500
    - device：scoped 类型的设备限定（同 get_record）

    返回：{start, direction, depth, nodes:[{entity_type, id, key, label, depth}],
    edges:[{from, to, relation}], truncated}。**边是扁平列表而不是嵌套树**：
    嵌套深了容易漏字段、也没法跨层比较，画图和推理都用扁平结构更稳。
    """
    if direction not in {"down", "up", "both"}:
        raise ToolError("direction 取 down / up / both")
    if not 1 <= depth <= MAX_DEPTH:
        raise ToolError(f"depth 取 1~{MAX_DEPTH}")
    if not 1 <= limit <= 500:
        raise ToolError("limit 取 1~500")

    spec = get_spec(entity_type)
    obj = resolve_one(spec, key, device)
    allowed = set(_parse_types(types)) if types else None

    nodes: list[dict[str, Any]] = [{"entity_type": entity_type, "id": obj.pk, "key": key_value(spec, obj), "label": spec.label, "depth": 0}]
    edges: list[dict[str, str]] = []
    seen: set[tuple[str, int]] = {(entity_type, obj.pk)}
    truncated = False
    frontier: list[tuple[str, Any]] = [(entity_type, obj)]

    for level in range(1, depth + 1):
        if truncated:
            break
        next_frontier: list[tuple[str, Any]] = []
        for current_type, current in frontier:
            moves: list[tuple[str, str, Any]] = []
            if direction in {"down", "both"}:
                moves += [(e.name, e.dst, e.forward) for e in edges_from(current_type)]
            if direction in {"up", "both"}:
                moves += [(e.name, e.src, e.reverse) for e in edges_to(current_type)]
            for relation, dst_type, getter in moves:
                if allowed is not None and dst_type not in allowed:
                    continue
                if truncated:
                    break
                for neighbour in getter(current):
                    ident = (dst_type, neighbour.pk)
                    if ident in seen:
                        continue
                    if len(nodes) >= limit:
                        truncated = True
                        break
                    seen.add(ident)
                    dst_spec = SPEC[dst_type]
                    nodes.append(
                        {
                            "entity_type": dst_type,
                            "id": neighbour.pk,
                            "key": key_value(dst_spec, neighbour),
                            "label": dst_spec.label,
                            "depth": level,
                        }
                    )
                    edges.append(
                        {
                            "from": f"{current_type}#{current.pk}",
                            "to": f"{dst_type}#{neighbour.pk}",
                            "relation": relation,
                        }
                    )
                    next_frontier.append((dst_type, neighbour))
        if not next_frontier:
            break
        frontier = next_frontier

    return {
        "start": {"entity_type": entity_type, "id": obj.pk, "key": key_value(spec, obj)},
        "direction": direction,
        "depth": depth,
        "nodes": nodes,
        "edges": edges,
        "truncated": truncated,
    }
