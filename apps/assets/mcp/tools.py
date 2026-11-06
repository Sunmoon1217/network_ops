"""资产域 MCP 工具（LLM 出口）。

注册模式与 Django admin 同构：``netops.mcp_server`` 持有根 server 单例（根注册表），
本模块顶层 ``@mcp.tool()`` 直接装饰（**import 即注册**，没有 register 包装函数）。
组合方（``netops/asgi.py`` 或测试）``import assets.mcp.tools`` 即完成接入；
``netops.mcp_server`` 严禁反向 import 本模块（防循环，硬规矩）。

## 为什么只有六个工具

实体表有 40+ 张，工具却压在 6 个，靠的是把「实体」下沉成数据（``assets.mcp.entities``）：
``find`` / ``list_records`` / ``get_record`` 覆盖全部登记类型，新增一张表只加一条
``EntitySpec``。真正需要独立工具的只有两类：

- **一次合成多份真值并做一致性判断**（``locate``）——查三次会让 LLM 拼错，比如把
  另一台交换机上同名口（``Gi1/0/5`` 每台都有）的 ARP 观测当成这台机器的端口。
- **多步查库 + 算法**（``relations`` 的变深遍历、``bundle`` 的横切拼装）——参数化的
  多跳查询不是 ``filters`` 能表达的。

判断标准就这一条：**能用 spec 的 ``filters`` / ``include`` 表达的，一律不新开工具**。

## 三条返回纪律

1. 列表给摘要，详情才给全字段（``detail=True``）。18 个字段 × 20 条是纯噪音。
2. 必须回 ``total``，让 LLM 知道有没有查全，否则它会拿首页当全集下结论。
3. 错误信息带可用值——粗粒度工具里 LLM 猜错枚举是常态，错误串是它唯一的纠正信号。

## 注解说明

上一版为每个工具写了 ``TypedDict``（``DeviceInfo`` 等），因为那时返回结构固定。
现在实体类型由 spec 驱动、字段随序列化器走，静态结构不存在了，所以统一用
``dict[str, Any]``——写一个假的 TypedDict 只会让类型检查放过真正的字段漂移。
字段口径的正确性改由「序列化器 + 测试」保证。
"""

import ipaddress
import re
from typing import Any

from django.db.models import Q, QuerySet
from django.utils import timezone
from mcp.server.mcpserver.exceptions import ToolError

from assets import models
from assets.mcp.entities import (
    MAX_DEPTH,
    MAX_PAGE_SIZE,
    SPEC,
    NodeType,
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
from netops.mcp_server import mcp, with_db_lifecycle

#: 单次关系展开 / 片段的返回条数上限：再多 LLM 也读不完，只是烧 token
MAX_ROWS = 50
#: 观测数据超过这个时长没刷新就提示「旧数据」，避免拿三个月前的 ARP 下结论
STALE_HOURS = 24


# ---------------------------------------------------------------------------
# 通用小工具
# ---------------------------------------------------------------------------


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


def _mac_variants(compact: str) -> list[str]:
    pairs = [compact[i : i + 2] for i in range(0, 12, 2)]
    # 点分形态是 3 组、每组 4 个十六进制（aabb.ccdd.eeff），所以按「两对一拼」走 0/2/4
    dotted = ".".join("".join(pairs[i : i + 2]) for i in range(0, 6, 2))
    return list(dict.fromkeys([":".join(pairs), "-".join(pairs), dotted, compact]))


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


# ---------------------------------------------------------------------------
# find：跨类型定位
# ---------------------------------------------------------------------------


@mcp.tool()
@with_db_lifecycle
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
    mac_variants = _mac_variants(_mac_compact(text)) if hint == "mac" else []

    hits: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for node_type in wanted:
        spec = SPEC[node_type]
        if not spec.search:
            continue
        cond = Q()
        for field in spec.search:
            cond |= Q(**{f"{field}__icontains": text})
        if node_type == NodeType.ARP_MAC and mac_variants:
            for variant in mac_variants:
                cond |= Q(mac_address__iexact=variant)
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


# ---------------------------------------------------------------------------
# list_records：通用列表
# ---------------------------------------------------------------------------


@mcp.tool()
@with_db_lifecycle
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


# ---------------------------------------------------------------------------
# get_record：单条详情 + 关系展开
# ---------------------------------------------------------------------------


@mcp.tool()
@with_db_lifecycle
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


# ---------------------------------------------------------------------------
# bundle：一个实体的横切面
# ---------------------------------------------------------------------------


@mcp.tool()
@with_db_lifecycle
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
        default = ("groups", "interfaces", "ip_addresses", "arp")
        wanted = [name for name in default if name in available] if spec.node_type == NodeType.DEVICE else available
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


# ---------------------------------------------------------------------------
# relations：变深图遍历
# ---------------------------------------------------------------------------


@mcp.tool()
@with_db_lifecycle
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

    nodes: list[dict[str, Any]] = [
        {"entity_type": entity_type, "id": obj.pk, "key": key_value(spec, obj), "label": spec.label, "depth": 0}
    ]
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


# ---------------------------------------------------------------------------
# locate：三方真值对账
# ---------------------------------------------------------------------------


@mcp.tool()
@with_db_lifecycle
def locate(target: str, limit: int = 20) -> dict[str, Any]:
    """定位一个 IP / MAC / 主机名「现在在哪」，并把登记与观测的冲突摆出来。

    回答的是三类数据的**一致性**，不是简单查表：

    - 登记（``IPAddress``）：这个地址规划给谁、状态是 used 还是 available
    - 观测（``ArpMac``）：哪些设备在哪个口看到过它——每台设备一份，同一地址可能多条
    - 台账（``Device.ip_address`` / ``Interface.ip_address``）：配置里写的是不是这个

    三者不一致才是最有价值的信息：登记为空却在线、同一地址对应多个 MAC、
    同一地址在多个端口被看到、ARP 表自己标记 conflict。

    参数：
    - target：IP（支持 IPv6）/ MAC（三种分隔符都认）/ 主机名。网段不行——那是
      ``find`` 或 ``list_records(entity_type="subnet")`` 的活
    - limit：观测条数上限，1~50

    返回：{target, kind, registry, observations, observed_total, devices, interfaces,
    conflicts, stale}。``registry`` 为 null 表示地址没登记；``stale=true`` 表示观测
    超过 24 小时没刷新，结论要打折。
    """
    text = (target or "").strip()
    if not text:
        raise ToolError("target 不能为空：可传 IP / MAC / 主机名")
    if not 1 <= limit <= 50:
        raise ToolError("limit 取 1~50")

    kind = _detect(text)
    if kind == "net":
        raise ToolError("locate 只接受单个地址 / MAC / 主机名；网段请用 find 或 list_records(entity_type='subnet')")

    ip = _parse_ip(text)
    mac = _mac_compact(text)

    registry: dict[str, Any] | None = None
    observations = models.ArpMac.objects.none()
    devices = models.Device.objects.none()
    interfaces = models.Interface.objects.none()

    if kind == "mac":
        cond = Q()
        for variant in _mac_variants(mac):
            cond |= Q(mac_address__iexact=variant)
        observations = models.ArpMac.objects.filter(cond).select_related("device").order_by("-updated_at")
    elif kind == "ip":
        hit = models.IPAddress.objects.filter(ip_address=ip).select_related("subnet", "device").first()
        if hit is not None:
            registry = {
                "ip_address": hit.ip_address,
                "status": hit.status,
                "status_display": hit.get_status_display(),
                "subnet": hit.subnet.network if hit.subnet else None,
                "device": hit.device.hostname if hit.device else None,
                "interface": hit.interface,
                "description": hit.description,
                "updated_at": hit.updated_at.isoformat(),
            }
        observations = models.ArpMac.objects.filter(ip_address=ip).select_related("device").order_by("-updated_at")
        devices = models.Device.objects.filter(ip_address=ip)
        interfaces = models.Interface.objects.filter(ip_address__icontains=ip)
    else:
        devices = models.Device.objects.filter(Q(hostname__icontains=text) | Q(remark__icontains=text))

    obs_rows = [
        {
            "device": item.device.hostname,
            "port": item.interface,
            "vlan": item.vlan,
            "ip": item.ip_address,
            "mac": item.mac_address,
            "arp_type": item.arp_type,
            "status": item.status,
            "learned_at": item.learned_at.isoformat() if item.learned_at else None,
            "updated_at": item.updated_at.isoformat(),
        }
        for item in observations[:limit]
    ]

    conflicts: list[str] = []
    macs = {row["mac"].lower() for row in obs_rows}
    ports = {(row["device"], row["port"]) for row in obs_rows if row["port"]}
    observed_devices = {row["device"] for row in obs_rows}

    if registry is not None:
        if registry["status"] != "used" and obs_rows:
            conflicts.append(f"登记状态为「{registry['status_display']}」，但被 {len(observed_devices)} 台设备观测到在线")
        if registry["device"] and observed_devices and registry["device"] not in observed_devices:
            conflicts.append(f"登记设备是 {registry['device']}，但观测到的设备是 {', '.join(sorted(observed_devices))}")
    elif obs_rows:
        conflicts.append("地址在线但未在 IPAddress 中登记")
    if len(macs) > 1:
        conflicts.append(f"同一地址对应 {len(macs)} 个不同 MAC：{', '.join(sorted(macs))}")
    if len(ports) > 1:
        conflicts.append(f"同一地址在 {len(ports)} 个端口被观测到（VM 迁移、双上联或环路，需人工确认）")
    if any(row["status"] == "conflict" for row in obs_rows):
        conflicts.append("ARP 表自身把该条标记为 conflict")

    stale = False
    if obs_rows:
        newest = max(item.updated_at for item in observations[:limit])
        stale = (timezone.now() - newest).total_seconds() > STALE_HOURS * 3600

    return {
        "target": text,
        "kind": kind,
        "registry": registry,
        "observations": obs_rows,
        "observed_total": observations.count(),
        "devices": [
            {"id": item.pk, "hostname": item.hostname, "device_type": item.device_type, "ip_address": item.ip_address}
            for item in devices[:limit]
        ],
        "interfaces": [
            {
                "device": item.device.hostname,
                "interface": item.interface,
                "ip_address": item.ip_address,
                "mode": item.mode,
            }
            for item in interfaces[:limit]
        ],
        "conflicts": conflicts,
        "stale": stale,
    }
