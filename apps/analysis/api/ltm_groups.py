"""LTM（SLB）主备设备组的配置合并接口（只读）。

把同一主备组（``ha`` / ``failover``）内多台 SLB 的 LTM 配置**逐层合并**成一行：

    VS（按 VS 名称去重）
      └─ 池（按池名并集去重）
          └─ 成员（按 名称 + 端口 并集去重）

组口径与合并信封复用 ``analysis.api.group_merge``：主备参与合并、单机/堆叠不参与；
每个合并条目都带 ``device``（出现它的设备主机名逗号拼接）、``inconsistent``、
``conflict_fields``。**列表型字段取并集**（profiles / iRules / 池 monitor），
**标量字段冲突取主机名第一台 + 标注**——LTM 的标量（地址/端口/模式）没有「并集值」，
与防火墙 ``policy_id`` 冲突口径一致；条目集合（VS/池/成员）则是并集。
"""

from __future__ import annotations

from datetime import date

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from analysis.api.analysis import _join_ip_port
from analysis.api.group_merge import HA_GROUP_TYPES, GroupKey, _differs, _join_devices, _union_lists, resolve_groups
from analysis.api.lb_chain import _xlsx_response
from assets.models import LtmPool, LtmPoolMember, LtmVirtualServer
from netops.pagination import StandardPagination

# VS 上逐字段比较的标量（profiles / rules 是列表，取并集不算冲突）
_VS_SCALARS = ("vs_address", "vs_port", "protocol", "status", "snat_type", "persist", "pool")

# 导出扁平宽表列（与前端 slb.vue 扁平列组手工保持一致，末列是「配置不一致」）
EXPORT_HEADERS = [
    "设备",
    "VS地址#端口",
    "VS名称",
    "协议",
    "SNAT",
    "会话保持",
    "Profile",
    "iRule",
    "关联池",
    "池负载模式",
    "池监控",
    "名称",
    "配置不一致",
]
EXPORT_COLUMN_WIDTHS = (24, 22, 24, 8, 12, 12, 30, 30, 16, 14, 22, 24, 12)


# ---------------------------------------------------------------------------
# 合并：成员 → 池 → VS
# ---------------------------------------------------------------------------


def _merge_members(pool_name: str, records, hostname: dict[int, str], order: dict[int, int]) -> list[dict]:
    """同一池的成员按（名称, 端口）并集去重；地址是标量，冲突取第一台并标注。"""
    occurrences: dict[tuple[str, str], list[LtmPoolMember]] = {}
    for _device_id, members in records:
        for member in members:
            occurrences.setdefault((member.name, member.port or ""), []).append(member)

    merged: list[dict] = []
    for (name, port), items in occurrences.items():
        items.sort(key=lambda member: order.get(member.device_id, 0))
        device_ids = [member.device_id for member in items]
        conflict_fields = []
        if _differs([member.address for member in items]):
            conflict_fields.append("address")
        first = items[0]
        merged.append(
            {
                "name": name,
                "address": first.address or "",
                "port": port,
                "device": _join_devices(device_ids, hostname),
                "device_ids": device_ids,
                "inconsistent": bool(conflict_fields),
                "conflict_fields": conflict_fields,
            }
        )
    return merged


def _merge_pools(vs_items, pools_by_key, members_by_key, hostname, order) -> list[dict]:
    """同一 VS 引用的池按池名并集去重（``vs_items`` 已按主机名序）。"""
    pool_names: list[str] = []
    seen: set[str] = set()
    for _device_id, virtual in vs_items:
        pool_name = virtual.pool or ""
        if pool_name and pool_name not in seen:
            seen.add(pool_name)
            pool_names.append(pool_name)

    merged: list[dict] = []
    for pool_name in pool_names:
        refs = [device_id for device_id, virtual in vs_items if (virtual.pool or "") == pool_name]
        records = [
            (device_id, pools_by_key[(device_id, pool_name)])
            for device_id in refs
            if (device_id, pool_name) in pools_by_key
        ]
        conflict_fields = []
        if _differs([record.mode for _device_id, record in records]):
            conflict_fields.append("mode")
        first = records[0][1] if records else None
        merged.append(
            {
                "name": pool_name,
                "device": _join_devices(refs, hostname),
                "device_ids": refs,
                "mode": first.mode if first else "",
                "monitors": _union_lists([record.monitors for _device_id, record in records]),
                "found": first is not None,
                "members": _merge_members(
                    pool_name,
                    [(device_id, members_by_key.get((device_id, pool_name), [])) for device_id in refs],
                    hostname,
                    order,
                ),
                "inconsistent": bool(conflict_fields),
                "conflict_fields": conflict_fields,
            }
        )
    return merged


def _merge_group(group: GroupKey) -> list[dict]:
    """一个主备组的全部 VS 合并行（每行 = 一个 VS 名的整条链）。"""
    device_ids = [device.pk for device in group.devices]
    hostname = {device.pk: device.hostname for device in group.devices}
    order = {device.pk: index for index, device in enumerate(group.devices)}

    vs_by_name: dict[str, list[LtmVirtualServer]] = {}
    for virtual in LtmVirtualServer.objects.filter(device_id__in=device_ids):
        vs_by_name.setdefault(virtual.name, []).append(virtual)

    pools_by_key = {(pool.device_id, pool.name): pool for pool in LtmPool.objects.filter(device_id__in=device_ids)}
    members_by_key: dict[tuple[int, str], list[LtmPoolMember]] = {}
    for member in LtmPoolMember.objects.filter(device_id__in=device_ids):
        members_by_key.setdefault((member.device_id, member.pool_name), []).append(member)

    rows: list[dict] = []
    for name, items in vs_by_name.items():
        items.sort(key=lambda virtual: order.get(virtual.device_id, 0))
        row_device_ids = [virtual.device_id for virtual in items]
        conflict_fields = [
            field for field in _VS_SCALARS if _differs([getattr(virtual, field) for virtual in items])
        ]
        first = items[0]
        rows.append(
            {
                "group": group.key,
                "group_name": group.name,
                "group_devices": [{"id": device.pk, "hostname": device.hostname} for device in group.devices],
                "device": _join_devices(row_device_ids, hostname),
                "device_ids": row_device_ids,
                "name": name,
                "vs_address": first.vs_address or "",
                "vs_port": first.vs_port or "",
                "protocol": first.protocol or "",
                "status": first.status or "",
                "snat_type": first.snat_type or "",
                "persist": first.persist or "",
                "profiles": _union_lists([virtual.profiles or [] for virtual in items]),
                "rules": _union_lists([virtual.rules or [] for virtual in items]),
                "pools": _merge_pools(
                    [(virtual.device_id, virtual) for virtual in items], pools_by_key, members_by_key, hostname, order
                ),
                "inconsistent": bool(conflict_fields),
                "conflict_fields": conflict_fields,
            }
        )
    rows.sort(key=lambda row: row["name"])
    return rows


# ---------------------------------------------------------------------------
# 过滤 / 搜索 / 排序
# ---------------------------------------------------------------------------


def _row_haystack(row: dict) -> str:
    parts: list[str] = [
        row["name"],
        row["vs_address"],
        row["vs_port"],
        row["protocol"],
        row["snat_type"],
        row["persist"],
        row["group_name"],
        row["device"],
        *row["profiles"],
        *row["rules"],
    ]
    parts += [device["hostname"] for device in row["group_devices"]]
    for pool in row["pools"]:
        parts += [pool["name"], pool["mode"], pool["device"], *pool["monitors"]]
        for member in pool["members"]:
            parts += [member["name"], member["address"], member["port"], member["device"]]
            if member["address"]:
                parts.append(_join_ip_port(member["address"], member["port"]))
                if member["port"]:
                    parts.append(f"{member['address']}:{member['port']}")
    return " ".join(str(part) for part in parts if part).lower()


def _filter_rows(rows: list[dict], request) -> list[dict]:
    protocol = (request.query_params.get("protocol") or "").strip()
    if protocol:
        rows = [row for row in rows if row["protocol"].lower() == protocol.lower()]
    status = (request.query_params.get("status") or "").strip()
    if status:
        rows = [row for row in rows if row["status"].lower() == status.lower()]
    search = (request.query_params.get("search") or "").strip()
    if search:
        needle = search.lower()
        rows = [row for row in rows if needle in _row_haystack(row)]
    return rows


def _order_rows(rows: list[dict], request) -> list[dict]:
    raw = (request.query_params.get("ordering") or "").strip()
    desc = raw.startswith("-")
    field = raw.lstrip("-")
    if field in {"name", "group_name", "device", "vs_address"}:
        rows.sort(key=lambda row: (row.get(field) or "", row["name"]), reverse=desc)
    else:
        rows.sort(key=lambda row: (row["group_name"], row["name"]))
    return rows


def _build_rows(request) -> list[dict]:
    raw_device = request.query_params.get("device")
    device_id: int | None = None
    if raw_device:
        try:
            device_id = int(raw_device)
        except (TypeError, ValueError):
            return []
    group_key = (request.query_params.get("group") or "").strip() or None

    rows = [
        row
        for group in resolve_groups("slb", HA_GROUP_TYPES, device_id=device_id, group_key=group_key)
        for row in _merge_group(group)
    ]
    return _order_rows(_filter_rows(rows, request), request)


# ---------------------------------------------------------------------------
# 接口
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([AllowAny])
def ltm_groups(request):
    """LTM 主备合并列表：
    GET /api/analysis/ltm-groups/?group=&device=&protocol=&status=&search=&ordering=&page=

    ``group`` 同时接受组键（``group-3`` / ``device-7``）与组名。
    """
    rows = _build_rows(request)
    paginator = StandardPagination()
    page = paginator.paginate_queryset(rows, request)
    return paginator.get_paginated_response(page if page is not None else [])


@api_view(["GET"])
@permission_classes([AllowAny])
def ltm_group_facets(request):
    """过滤下拉选项：GET /api/analysis/ltm-groups/facets/

    ``groups`` 是主备组名 / 单机 SLB 名（页面按组过滤）；``protocols`` / ``statuses``
    取自 VS 的去重值。
    """
    groups = [
        {
            "key": group.key,
            "name": group.name,
            "group_id": group.group_id,
            "devices": [device.hostname for device in group.devices],
        }
        for group in resolve_groups("slb", HA_GROUP_TYPES)
    ]
    protocols = sorted({value for value in LtmVirtualServer.objects.values_list("protocol", flat=True) if value})
    statuses = sorted({value for value in LtmVirtualServer.objects.values_list("status", flat=True) if value})
    return Response({"groups": groups, "protocols": protocols, "statuses": statuses})


def _flat_rows(rows: list[dict]) -> list[list]:
    """扁平宽表：粒度规则与旧 SLB 导出一致（以链最深层为行、字段下填），
    设备列是合并后的逗号拼接串；末列取该行路径上任一层的不一致。"""
    flat: list[list] = []
    for row in rows:
        vs_label = _join_ip_port(row["vs_address"], row["vs_port"]) if row["vs_address"] else row["name"]
        base = [
            row["device"],
            vs_label,
            row["name"],
            row["protocol"] or "-",
            row["snat_type"] or "-",
            row["persist"] or "-",
            "、".join(row["profiles"]) or "-",
            "、".join(row["rules"]) or "-",
        ]
        if not row["pools"]:
            flat.append(base + ["-", "-", "-", vs_label, "是" if row["inconsistent"] else ""])
            continue
        for pool in row["pools"]:
            pool_flag = row["inconsistent"] or pool["inconsistent"]
            pool_seg = [pool["name"], pool["mode"] or "-", "、".join(pool["monitors"]) or "-"]
            if not pool["members"]:
                flat.append(base + pool_seg + [pool["name"], "是" if pool_flag else ""])
                continue
            for member in pool["members"]:
                label = _join_ip_port(member["address"], member["port"]) if member["address"] else member["name"]
                flag = "是" if (pool_flag or member["inconsistent"]) else ""
                flat.append(base + pool_seg + [label, flag])
    return flat


@api_view(["GET"])
@permission_classes([AllowAny])
def ltm_group_export(request):
    """导出主备合并后的扁平宽表：
    GET /api/analysis/ltm-groups/export/?group=&device=&protocol=&status=&search=
    """
    rows = _build_rows(request)
    return _xlsx_response(
        EXPORT_HEADERS,
        EXPORT_COLUMN_WIDTHS,
        _flat_rows(rows),
        "LTM 主备关联链",
        f"ltm-groups-{date.today():%Y%m%d}.xlsx",
    )
