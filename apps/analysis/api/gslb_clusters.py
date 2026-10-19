"""GSLB 集群分析接口（只读）。

把同一 GSLB 集群内多台设备的 GTM 配置**逐层合并**成一行：

    WideIP（按 域名 + 记录类型 去重）
      └─ 池（按池名并集去重）
          └─ 成员（按 server/vserver 并集去重）

集群口径：``DeviceGroup.group_type == "cluster"`` 的组成员（只取 ``device_type == "gslb"``
的设备）；不在任何集群组里的 GSLB 设备各自成为一个**单机集群**（集群名取设备 hostname，
集群键 ``device-<id>``）——需求口径「单机 gslb 也算集群」。同一设备若落在多个集群组里，
按组名 + id 排序取第一个（其余组忽略，已在文档与测试里固定）。

合并规则：

- 每个合并条目的 ``device`` 字段 = **出现该条目的设备主机名用英文逗号拼接**
  （按主机名排序，如 ``gtm-a,gtm-b``）；
- 标量字段以**主机名排序第一台**设备的取值为准；
- 同名条目的标量 / 子集合不一致时，条目带 ``inconsistent: true`` 与
  ``conflict_fields``（列出不一致的字段名），前端据此打「配置不一致」标记；
- 列表型字段（池 monitor、成员 monitor 合集）取并集去重，不算冲突。

URL 前缀 ``/api/analysis/`` 是本接口新开的独立前缀：合并口径与返回结构都带上了
cluster 维度，刻意不混进 ``/api/lb-chain/gslb/``（旧接口 / 旧页面零影响）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from analysis.api.analysis import _join_ip_port, _parse_member_entry
from analysis.api.lb_chain import _xlsx_response, gtm_facet_values
from assets.models import Device, DeviceGroup, GtmPool, GtmServer, GtmVServer, GtmWideip
from netops.pagination import StandardPagination

# 合并条目 device 字段的分隔符：多台设备用半角逗号拼接（如 gtm-a,gtm-b）
DEVICE_SEPARATOR = ","

# 集群口径：只认 group_type=cluster 的设备组
CLUSTER_GROUP_TYPE = "cluster"

# 成员标量字段的两种历史写法：Saver 归一后是 order/ratio/status/monitor，
# 手工 payload / 旧模板给的是 member_ 前缀（与旧接口同口径）
_MEMBER_SCALARS = ("order", "ratio", "status", "monitor")

# 池记录里逐字段比较的标量（monitor 是列表，取并集不算冲突）
_POOL_SCALARS = ("lb_mode", "alternate_mode", "fallback_mode", "fallback_ip", "ttl")

_STATE_LABELS = {"ok": "正常", "disabled": "停用", "lost": "未找到"}

# 导出扁平宽表列（与前端 gslb.vue 扁平列组手工保持一致，末列是本接口新增的「配置不一致」）
CLUSTER_EXPORT_HEADERS = [
    "设备",
    "域名",
    "记录类型",
    "WideIP算法",
    "池Order",
    "池Ratio",
    "池名",
    "池监控",
    "池算法",
    "fallback",
    "TTL",
    "名称",  # 成员地址#端口；回退行是池名 / 域名
    "成员Order",
    "成员Ratio",
    "成员监控",
    "数据中心",
    "状态",
    "配置不一致",
]
CLUSTER_EXPORT_COLUMN_WIDTHS = (28, 24, 10, 14, 10, 10, 16, 22, 24, 20, 8, 24, 12, 12, 14, 14, 10, 12)


# ---------------------------------------------------------------------------
# 集群划分
# ---------------------------------------------------------------------------


@dataclass
class Cluster:
    """一个 GSLB 集群：一台（单机）或多台设备。"""

    key: str  # "group-<id>" / "device-<id>"
    name: str  # 集群组名 / 单机设备 hostname
    group_id: int | None
    devices: list[Device]  # 已按 hostname 排序


def _resolve_clusters(device_id: int | None = None, cluster_key: str | None = None) -> list[Cluster]:
    """把 GSLB 设备划分成集群；``device_id`` / ``cluster_key`` 用于收窄范围。

    - 设备只在 ``group_type=cluster`` 的组里成团；同组多台设备即一个集群；
    - 一台设备出现在多个集群组时，取（组名, id）排序第一个，其余组忽略（否则一台设备
      会同时出现在两个集群里、行数与 device 拼接都不稳定）；
    - 未入集群组的 GSLB 设备各自成为单机集群。
    """
    gslb_devices = {device.pk: device for device in Device.objects.filter(device_type="gslb")}
    clusters: dict[str, Cluster] = {}
    assigned: set[int] = set()

    groups = DeviceGroup.objects.filter(group_type=CLUSTER_GROUP_TYPE).prefetch_related("members__device")
    for group in groups.order_by("name", "id"):
        members = sorted(
            (m.device for m in group.members.all() if m.device_id in gslb_devices and m.device_id not in assigned),
            key=lambda device: device.hostname,
        )
        if not members:
            continue
        for device in members:
            assigned.add(device.pk)
        clusters[f"group-{group.pk}"] = Cluster(
            key=f"group-{group.pk}", name=group.name, group_id=group.pk, devices=members
        )

    for device in sorted(gslb_devices.values(), key=lambda item: item.hostname):
        if device.pk not in assigned:
            clusters[f"device-{device.pk}"] = Cluster(
                key=f"device-{device.pk}", name=device.hostname, group_id=None, devices=[device]
            )

    resolved = sorted(clusters.values(), key=lambda cluster: (cluster.name, cluster.key))
    if cluster_key:
        # 同时认集群键（group-3 / device-7）与组名——前端下拉用键，人工调接口更顺手写组名
        return [cluster for cluster in resolved if cluster.key == cluster_key or cluster.name == cluster_key]
    if device_id is not None:
        return [cluster for cluster in resolved if any(device.pk == device_id for device in cluster.devices)]
    return resolved


def cluster_options() -> list[dict]:
    """过滤下拉用的集群选项：集群组名 / 单机设备名（按名字排序，与列表默认序一致）。

    单机集群的 ``group_id`` 为 null，前端可据此区分「集群组」与「单机」。
    """
    return [
        {
            "key": cluster.key,
            "name": cluster.name,
            "group_id": cluster.group_id,
            "devices": [device.hostname for device in cluster.devices],
        }
        for cluster in _resolve_clusters()
    ]


# ---------------------------------------------------------------------------
# 合并工具
# ---------------------------------------------------------------------------


def _differs(values) -> bool:
    """一组取值是否不一致：None / 空串 / 数字 / 列表都能比较（JSON 归一后去重）。"""
    seen = {json.dumps(value, sort_keys=True, default=str) for value in values}
    return len(seen) > 1


def _union_lists(values) -> list:
    """多个列表按序并集去重（monitor 这类列表字段用）。"""
    union: list = []
    for items in values:
        for item in items or []:
            if item not in union:
                union.append(item)
    return union


def _uniq_join(values) -> str:
    """去重排序后顿号连接，空集返回 ``-``（导出宽表的池级 Order/Ratio 用）。"""
    items = sorted({value for value in values if value is not None})
    return "、".join(str(item) for item in items) or "-"


def _member_key(entry) -> tuple[str, str]:
    """成员身份 = (server, vserver)，成员条目的三种历史形态由 ``_parse_member_entry`` 归一。"""
    server_name, vs_name, _raw = _parse_member_entry(entry)
    return server_name, vs_name


def _member_scalar(raw: dict, field: str):
    """成员标量取值：优先规范键，空值再回退 ``member_`` 前缀（旧接口同口径）。"""
    primary, fallback = field, f"member_{field}"
    if field in ("status", "monitor"):
        return str(raw.get(primary) or raw.get(fallback) or "")
    return raw.get(primary, raw.get(fallback))


# ---------------------------------------------------------------------------
# 逐层合并：成员 → 池 → WideIP
# ---------------------------------------------------------------------------


def _merge_members(pool_records, vservers, server_info, hostname, order) -> tuple[list[dict], list[str]]:
    """把同集群内同一池的成员按 (server, vserver) 并集去重。

    ``pool_records`` 是 ``[(device_id, GtmPool)]``（已按主机名序）。返回
    ``(成员行列表, 该池涉及的 monitor 合集)``——monitor 合集含成员自身 + 解析到的
    虚拟服务器 / 服务器 monitor，供 ``?monitor=`` 过滤（与旧接口的三处口径对齐）。
    """
    occurrences: dict[tuple[str, str], list[tuple[int, dict]]] = {}
    for device_id, record in pool_records:
        for entry in record.members or []:
            server_name, vs_name, raw = _parse_member_entry(entry)
            occurrences.setdefault((server_name, vs_name), []).append((device_id, raw))

    members: list[dict] = []
    monitors: list[str] = []
    for (server_name, vs_name), occ in occurrences.items():
        occ.sort(key=lambda item: order.get(item[0], 0))
        device_ids = [device_id for device_id, _raw in occ]

        conflict_fields = []
        scalars: dict[str, object] = {}
        for field in _MEMBER_SCALARS:
            values = [_member_scalar(raw, field) for _device_id, raw in occ]
            if _differs(values):
                conflict_fields.append(field)
            scalars[field] = values[0]

        # 地址 / 端口 / 数据中心：逐台解析，取主机名序第一台能解出地址的设备
        resolved = []
        for device_id in device_ids:
            vserver = vservers.get((device_id, server_name, vs_name))
            address = str(vserver.ip_address) if vserver and vserver.ip_address else None
            port = (vserver.port if vserver else "") or ""
            datacenter, server_monitor = server_info.get((device_id, server_name), ("", ""))
            resolved.append((address, port, datacenter))
            if vserver and vserver.monitor:
                monitors.append(vserver.monitor)
            if server_monitor:
                monitors.append(server_monitor)
        # 同一成员在不同设备上地址/端口不同 → 标为配置不一致
        if _differs([(address, port) for address, port, _dc in resolved]):
            conflict_fields.append("address")

        target = next((item for item in resolved if item[0]), (None, "", ""))
        members.append(
            {
                "server": server_name,
                "vserver": vs_name,
                "device": DEVICE_SEPARATOR.join(hostname[device_id] for device_id in device_ids),
                "device_ids": device_ids,
                "status": scalars["status"],
                "order": scalars["order"],
                "ratio": scalars["ratio"],
                "monitor": scalars["monitor"],
                "address": target[0],
                "port": target[1],
                "datacenter": target[2],
                "found": target[0] is not None,
                "inconsistent": bool(conflict_fields),
                "conflict_fields": conflict_fields,
            }
        )

    return members, monitors


def _merge_pools(items, pools, vservers, server_info, hostname, order) -> list[dict]:
    """把同集群内同一 WideIP 引用的池按池名并集去重。

    ``items`` 是同一 (域名, rtype) 下的 ``GtmWideip`` 列表（已按主机名序）。
    """
    pool_names: list[str] = []
    seen: set[str] = set()
    for wideip in items:
        for entry in wideip.pool_entries():
            if entry["name"] not in seen:
                seen.add(entry["name"])
                pool_names.append(entry["name"])

    merged: list[dict] = []
    for pool_name in pool_names:
        refs = [wideip for wideip in items if pool_name in wideip.pool_names]
        ref_ids = [wideip.device_id for wideip in refs]
        entries: dict[int, dict] = {}
        for wideip in refs:
            for entry in wideip.pool_entries():
                if entry["name"] == pool_name:
                    entries[wideip.device_id] = entry

        conflict_fields = []
        # wideip 级权重：不同设备对同一池的 order/ratio 可以不同
        for field in ("order", "ratio"):
            if _differs([entries[device_id].get(field) for device_id in ref_ids]):
                conflict_fields.append(field)

        records = [
            (device_id, pools[(device_id, pool_name)]) for device_id in ref_ids if (device_id, pool_name) in pools
        ]
        for field in _POOL_SCALARS:
            if _differs([getattr(record, field) for _device_id, record in records]):
                conflict_fields.append(field)
        member_sets = [
            tuple(sorted(_member_key(entry) for entry in (record.members or []))) for _device_id, record in records
        ]
        if _differs(member_sets):
            conflict_fields.append("members")

        members, member_monitors = _merge_members(records, vservers, server_info, hostname, order)
        first = records[0][1] if records else None
        merged.append(
            {
                "name": pool_name,
                "device": DEVICE_SEPARATOR.join(hostname[device_id] for device_id in ref_ids),
                "device_ids": ref_ids,
                "order": entries[ref_ids[0]].get("order") if ref_ids else None,
                "ratio": entries[ref_ids[0]].get("ratio") if ref_ids else None,
                "lb_mode": first.lb_mode if first else "",
                "alternate_mode": first.alternate_mode if first else "",
                "fallback_mode": first.fallback_mode if first else "",
                "fallback_ip": (first.fallback_ip if first else None) or "",
                "ttl": first.ttl if first else None,
                "monitor": _union_lists([record.monitor for _device_id, record in records]),
                "found": first is not None,
                "members": members,
                "inconsistent": bool(conflict_fields),
                "conflict_fields": conflict_fields,
                "_monitors": member_monitors,
            }
        )
    return merged


def _merge_cluster(cluster: Cluster) -> list[dict]:
    """一个集群的全部 WideIP 合并行（每行 = 一个 (域名, rtype) 的整条链）。"""
    devices = cluster.devices
    device_ids = [device.pk for device in devices]
    hostname = {device.pk: device.hostname for device in devices}
    order = {device.pk: index for index, device in enumerate(devices)}

    wideips: dict[tuple[str, str], list[GtmWideip]] = {}
    for wideip in GtmWideip.objects.filter(device_id__in=device_ids):
        wideips.setdefault((wideip.name, wideip.rtype), []).append(wideip)

    pools = {(pool.device_id, pool.name): pool for pool in GtmPool.objects.filter(device_id__in=device_ids)}
    server_info = {
        (server.device_id, server.name): (server.datacenter or "", server.monitor or "")
        for server in GtmServer.objects.filter(device_id__in=device_ids)
    }
    vservers = {
        (vserver.device_id, vserver.server.name, vserver.name): vserver
        for vserver in GtmVServer.objects.filter(device_id__in=device_ids).select_related("server")
    }

    rows: list[dict] = []
    for (name, rtype), items in wideips.items():
        items.sort(key=lambda wideip: order.get(wideip.device_id, 0))
        row_device_ids = [wideip.device_id for wideip in items]

        conflict_fields = []
        if _differs([wideip.lb_mode for wideip in items]):
            conflict_fields.append("lb_mode")
        # 同域名在集群内引用的池集合不同 → 标记（并集展示，但差异要可见）
        if _differs([tuple(sorted(wideip.pool_names)) for wideip in items]):
            conflict_fields.append("pools")

        merged_pools = _merge_pools(items, pools, vservers, server_info, hostname, order)
        monitors = _union_lists([pool["monitor"] + pool.pop("_monitors") for pool in merged_pools])
        rows.append(
            {
                "cluster": cluster.key,
                "cluster_name": cluster.name,
                "cluster_devices": [{"id": device.pk, "hostname": device.hostname} for device in devices],
                "device": DEVICE_SEPARATOR.join(hostname[device_id] for device_id in row_device_ids),
                "device_ids": row_device_ids,
                "name": name,
                "rtype": rtype or "",
                "lb_mode": items[0].lb_mode or "",
                "monitors": monitors,
                "pools": merged_pools,
                "inconsistent": bool(conflict_fields),
                "conflict_fields": conflict_fields,
            }
        )

    rows.sort(key=lambda row: row["name"])
    return rows


# ---------------------------------------------------------------------------
# 过滤 / 搜索 / 排序（合并后在内存里做：GSLB 数据量小，且合并行的字段跨多表）
# ---------------------------------------------------------------------------


def _row_haystack(row: dict) -> str:
    """把一行的全部可搜字段拼成小写文本（成员地址同时给 ``#`` 与 ``:`` 两种拼法）。"""
    parts: list[str] = [
        row["name"],
        row["rtype"],
        row["lb_mode"],
        row["cluster_name"],
        row["device"],
        *row["monitors"],
    ]
    parts += [device["hostname"] for device in row["cluster_devices"]]
    for pool in row["pools"]:
        parts += [
            pool["name"],
            pool["lb_mode"],
            pool["alternate_mode"],
            pool["fallback_mode"],
            pool["fallback_ip"] or "",
            pool["device"],
            *pool["monitor"],
        ]
        for member in pool["members"]:
            parts += [member["server"], member["vserver"], member["monitor"], member["datacenter"], member["device"]]
            if member["address"]:
                parts.append(str(member["address"]))
                parts.append(_join_ip_port(member["address"], member["port"]))
                if member["port"]:
                    parts.append(f"{member['address']}:{member['port']}")
    return " ".join(str(part) for part in parts if part).lower()


def _filter_rows(rows: list[dict], request) -> list[dict]:
    """``?rtype=`` / ``?monitor=`` / ``?search=`` 三个过滤（语义对齐旧接口）。"""
    rtype = (request.query_params.get("rtype") or "").strip()
    if rtype:
        rows = [row for row in rows if row["rtype"].lower() == rtype.lower()]
    monitor = (request.query_params.get("monitor") or "").strip()
    if monitor:
        needle = monitor.lower()
        rows = [row for row in rows if any(needle in str(item).lower() for item in row["monitors"])]
    search = (request.query_params.get("search") or "").strip()
    if search:
        needle = search.lower()
        rows = [row for row in rows if needle in _row_haystack(row)]
    return rows


def _order_rows(rows: list[dict], request) -> list[dict]:
    """``?ordering=`` 支持 name / cluster_name / device；未知字段回退「集群名 + 域名」。"""
    raw = (request.query_params.get("ordering") or "").strip()
    desc = raw.startswith("-")
    field = raw.lstrip("-")
    if field in {"name", "cluster_name", "device"}:
        rows.sort(key=lambda row: (row.get(field) or "", row["cluster_name"], row["name"]), reverse=desc)
    else:
        rows.sort(key=lambda row: (row["cluster_name"], row["name"]))
    return rows


def _build_rows(request) -> list[dict]:
    """按查询参数划分集群 → 逐集群合并 → 过滤 → 排序，返回全量合并行。"""
    raw_device = request.query_params.get("device")
    device_id: int | None = None
    if raw_device:
        try:
            device_id = int(raw_device)
        except (TypeError, ValueError):
            return []  # 设备 id 非法 = 无匹配，不静默退化成全量
    cluster_key = (request.query_params.get("cluster") or "").strip() or None

    rows = [
        row
        for cluster in _resolve_clusters(device_id=device_id, cluster_key=cluster_key)
        for row in _merge_cluster(cluster)
    ]
    return _order_rows(_filter_rows(rows, request), request)


# ---------------------------------------------------------------------------
# 接口
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([AllowAny])
def gslb_clusters(request):
    """GSLB 集群合并列表：
    GET /api/analysis/gslb-clusters/?device=&cluster=&rtype=&monitor=&search=&ordering=&page=

    ``cluster`` 同时接受集群键（``group-3`` / ``device-7``）与组名；``device`` 用在
    「按设备反查其所属集群」的场景（前端页面已改用 ``cluster`` 组名过滤）。
    """
    rows = _build_rows(request)
    paginator = StandardPagination()
    page = paginator.paginate_queryset(rows, request)
    return paginator.get_paginated_response(page if page is not None else [])


@api_view(["GET"])
@permission_classes([AllowAny])
def gslb_cluster_facets(request):
    """过滤下拉选项：GET /api/analysis/gslb-clusters/facets/

    ``rtypes`` / ``monitors`` 与旧 GSLB 接口同口径（共用 ``gtm_facet_values``）；
    额外给 ``clusters``——GSLB 页面用「集群组名 / 单机设备名」做过滤器，而不是逐台设备。
    """
    return Response({**gtm_facet_values(), "clusters": cluster_options()})


def _cluster_flat_rows(rows: list[dict]) -> list[list]:
    """扁平宽表：粒度规则与旧 GSLB 导出一致（以链最深层为行、字段下填），
    设备列是合并后的逗号拼接串；末列「配置不一致」取该行路径上任一层的不一致
    （wideip / 池 / 成员），否则池内成员漂移会被 wideip 层的不一致掩盖。"""
    flat: list[list] = []
    for row in rows:
        wide = [row["device"], row["name"], row["rtype"] or "-", row["lb_mode"] or "-"]
        empty_pool = ["-"] * 7  # 池Order/池Ratio/池名/池监控/池算法/fallback/TTL
        empty_member = ["", "", "", "", "-"]  # 成员Order/成员Ratio/成员监控/数据中心/状态
        if not row["pools"]:
            flat.append(wide + empty_pool + [row["name"]] + empty_member + ["是" if row["inconsistent"] else ""])
            continue
        for pool in row["pools"]:
            algo = " / ".join(item for item in (pool["lb_mode"], pool["alternate_mode"]) if item) or "-"
            fallback = (pool["fallback_mode"] or "") + (f"（{pool['fallback_ip']}）" if pool["fallback_ip"] else "")
            pool_flag = row["inconsistent"] or pool["inconsistent"]
            pool_seg = [
                _uniq_join(member["order"] for member in pool["members"]),
                _uniq_join(member["ratio"] for member in pool["members"]),
                pool["name"],
                "、".join(pool["monitor"]) or "-",
                algo,
                fallback or "-",
                str(pool["ttl"]) if pool["ttl"] is not None else "-",
            ]
            if not pool["members"]:
                flat.append(wide + pool_seg + [pool["name"]] + empty_member + ["是" if pool_flag else ""])
                continue
            for member in pool["members"]:
                label = (
                    _join_ip_port(member["address"], member["port"])
                    if member["found"] and member["address"]
                    else f"{member['server']}/{member['vserver']}"
                )
                state_key = "lost" if not member["found"] else ("disabled" if member["status"] == "disabled" else "ok")
                member_seg = [
                    "" if member["order"] is None else str(member["order"]),
                    "" if member["ratio"] is None else str(member["ratio"]),
                    member["monitor"],
                    member["datacenter"],
                    _STATE_LABELS.get(state_key, "-"),
                ]
                flag = "是" if (pool_flag or member["inconsistent"]) else ""
                flat.append(wide + pool_seg + [label] + member_seg + [flag])
    return flat


@api_view(["GET"])
@permission_classes([AllowAny])
def gslb_cluster_export(request):
    """导出集群合并后的扁平宽表：
    GET /api/analysis/gslb-clusters/export/?device=&cluster=&rtype=&monitor=&search=
    """
    rows = _build_rows(request)
    return _xlsx_response(
        CLUSTER_EXPORT_HEADERS,
        CLUSTER_EXPORT_COLUMN_WIDTHS,
        _cluster_flat_rows(rows),
        "GSLB 集群关联链",
        f"gslb-clusters-{date.today():%Y%m%d}.xlsx",
    )
