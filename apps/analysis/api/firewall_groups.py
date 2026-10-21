"""防火墙主备设备组的配置合并接口（只读）。

把同一主备组（``ha`` / ``failover``）内多台防火墙（各厂商，``device_type=firewall``）的
**策略 / NAT 规则**合并成一行：

- **策略按 ``policy_id`` 去重**（``Policy`` 的自然键是 ``(device, policy_id)``）；
  同一 policy_id 在两台上内容不同时**取主机名第一台 + 标注**——策略是有序的，并集会把
  顺序语义搞坏，这正是与 GTM/LTM「集合并集」不同的地方；
- **NAT 规则按 ``order`` 去重**（``NatRule`` 的自然键是 ``(device, order)``，名字不唯一）；
- 三个 M2M（源/目的地址、服务）与 ``translated_*`` 也按「第一台 + 标注」比较；
- 每个合并条目都带 ``device``（出现它的设备主机名逗号拼接）、``inconsistent``、
  ``conflict_fields``。

组口径复用 ``analysis.api.group_merge``：主备参与合并、单机/堆叠不参与、未入组设备
各自成单机组。展示串复用 assets 序列化器的格式化助手，保证与旧页面口径一致。
"""

from __future__ import annotations

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from analysis.api.group_merge import HA_GROUP_TYPES, GroupKey, _differs, _join_devices, resolve_groups
from assets.api.serializers import _format_address_entry, _format_service_entry
from assets.models import NatRule, Policy
from netops.pagination import StandardPagination

# 策略 / NAT 的标量比较字段（M2M 另算）
_POLICY_SCALARS = ("order", "name", "action", "enabled", "log", "description")
_NAT_SCALARS = ("order", "name", "nat_type", "enabled", "description")

# NAT 的翻译引用字段（AddressBook / Service 的名字）
_NAT_TRANSLATED = ("translated_source", "translated_destination", "translated_service")


# ---------------------------------------------------------------------------
# 比较 / 展示助手
# ---------------------------------------------------------------------------


def _address_signature(entry) -> tuple[str, ...]:
    """地址簿条目的**内容**签名（不含 pk——不同设备上的 pk 必然不同）。"""
    return (
        entry.name or "",
        entry.address_type or "",
        str(entry.ip_address or ""),
        "" if entry.ip_netmask is None else str(entry.ip_netmask),
        str(entry.ip_start or ""),
        str(entry.ip_end or ""),
    )


def _service_signature(entry) -> tuple[str, ...]:
    """服务条目的内容签名（一个服务名允许多行端口定义）。"""
    return (entry.name or "", entry.protocol or "", entry.port or "", entry.port2 or "")


def _address_set(policy_or_rule, field: str) -> tuple[tuple[str, ...], ...]:
    return tuple(sorted(_address_signature(entry) for entry in getattr(policy_or_rule, field).all()))


def _service_set(policy_or_rule, field: str) -> tuple[tuple[str, ...], ...]:
    return tuple(sorted(_service_signature(entry) for entry in getattr(policy_or_rule, field).all()))


def _display_addresses(policy_or_rule, field: str) -> list[str]:
    return [_format_address_entry(entry) for entry in getattr(policy_or_rule, field).all()]


def _display_services(policy_or_rule, field: str) -> list[str]:
    return [_format_service_entry(entry) for entry in getattr(policy_or_rule, field).all()]


def _translated_name(rule, field: str) -> str:
    target = getattr(rule, field)
    if not target:
        return ""
    return getattr(target, "name", "") or ""


# ---------------------------------------------------------------------------
# 合并：策略 / NAT 规则
# ---------------------------------------------------------------------------


def _merge_policies(group: GroupKey) -> list[dict]:
    device_ids = [device.pk for device in group.devices]
    hostname = {device.pk: device.hostname for device in group.devices}
    order = {device.pk: index for index, device in enumerate(group.devices)}

    by_pid: dict[str, list[Policy]] = {}
    for policy in Policy.objects.filter(device_id__in=device_ids).prefetch_related(
        "source_addresses", "destination_addresses", "services"
    ):
        by_pid.setdefault(policy.policy_id, []).append(policy)

    rows: list[dict] = []
    for policy_id, items in by_pid.items():
        items.sort(key=lambda policy: order.get(policy.device_id, 0))
        row_device_ids = [policy.device_id for policy in items]
        conflict_fields = [
            field for field in _POLICY_SCALARS if _differs([getattr(policy, field) for policy in items])
        ]
        for field in ("source_addresses", "destination_addresses", "services"):
            getter = _service_set if field == "services" else _address_set
            if _differs([getter(policy, field) for policy in items]):
                conflict_fields.append(field)
        first = items[0]
        rows.append(
            {
                "group": group.key,
                "group_name": group.name,
                "group_devices": [{"id": device.pk, "hostname": device.hostname} for device in group.devices],
                "device": _join_devices(row_device_ids, hostname),
                "device_ids": row_device_ids,
                "policy_id": policy_id,
                # 合并行对应每台设备各一条 Policy 记录：访问流「展开」要按这些主键一起过滤
                "policy_pks": [policy.pk for policy in items],
                "order": first.order,
                "name": first.name or "",
                "action": first.action,
                "enabled": first.enabled,
                "log": first.log,
                "description": first.description or "",
                "source_addresses_display": _display_addresses(first, "source_addresses"),
                "destination_addresses_display": _display_addresses(first, "destination_addresses"),
                "services_display": _display_services(first, "services"),
                "inconsistent": bool(conflict_fields),
                "conflict_fields": conflict_fields,
            }
        )
    rows.sort(key=lambda row: (row["order"], row["policy_id"]))
    return rows


def _merge_nat_rules(group: GroupKey) -> list[dict]:
    device_ids = [device.pk for device in group.devices]
    hostname = {device.pk: device.hostname for device in group.devices}
    order = {device.pk: index for index, device in enumerate(group.devices)}

    by_order: dict[int, list[NatRule]] = {}
    rules = (
        NatRule.objects.filter(device_id__in=device_ids)
        .select_related("translated_source", "translated_destination", "translated_service")
        .prefetch_related("source_addresses", "destination_addresses", "services")
    )
    for rule in rules:
        by_order.setdefault(rule.order, []).append(rule)

    rows: list[dict] = []
    for rule_order, items in by_order.items():
        items.sort(key=lambda rule: order.get(rule.device_id, 0))
        row_device_ids = [rule.device_id for rule in items]
        conflict_fields = [
            field for field in _NAT_SCALARS if _differs([getattr(rule, field) for rule in items])
        ]
        for field in ("source_addresses", "destination_addresses", "services"):
            getter = _service_set if field == "services" else _address_set
            if _differs([getter(rule, field) for rule in items]):
                conflict_fields.append(field)
        for field in _NAT_TRANSLATED:
            if _differs([_translated_name(rule, field) for rule in items]):
                conflict_fields.append(field)
        first = items[0]
        rows.append(
            {
                "group": group.key,
                "group_name": group.name,
                "group_devices": [{"id": device.pk, "hostname": device.hostname} for device in group.devices],
                "device": _join_devices(row_device_ids, hostname),
                "device_ids": row_device_ids,
                "order": rule_order,
                "name": first.name or "",
                "nat_type": first.nat_type,
                "enabled": first.enabled,
                "description": first.description or "",
                "source_addresses_display": _display_addresses(first, "source_addresses"),
                "destination_addresses_display": _display_addresses(first, "destination_addresses"),
                "services_display": _display_services(first, "services"),
                "translated_source": _translated_name(first, "translated_source"),
                "translated_destination": _translated_name(first, "translated_destination"),
                "translated_service": _translated_name(first, "translated_service"),
                "inconsistent": bool(conflict_fields),
                "conflict_fields": conflict_fields,
            }
        )
    rows.sort(key=lambda row: (row["order"], row["name"]))
    return rows


# ---------------------------------------------------------------------------
# 过滤 / 搜索 / 排序
# ---------------------------------------------------------------------------


def _policy_haystack(row: dict) -> str:
    parts = [
        row["policy_id"],
        row["name"],
        row["action"],
        row["description"],
        row["group_name"],
        row["device"],
        *row["source_addresses_display"],
        *row["destination_addresses_display"],
        *row["services_display"],
    ]
    parts += [device["hostname"] for device in row["group_devices"]]
    return " ".join(str(part) for part in parts if part).lower()


def _nat_haystack(row: dict) -> str:
    parts = [
        row["name"],
        row["nat_type"],
        row["description"],
        row["translated_source"],
        row["translated_destination"],
        row["translated_service"],
        row["group_name"],
        row["device"],
        *row["source_addresses_display"],
        *row["destination_addresses_display"],
        *row["services_display"],
    ]
    parts += [device["hostname"] for device in row["group_devices"]]
    return " ".join(str(part) for part in parts if part).lower()


def _narrow_groups(request) -> list[GroupKey]:
    """``?group=`` / ``?device=`` 收窄到设备组（device 非法直接返回空集）。"""
    raw_device = request.query_params.get("device")
    device_id: int | None = None
    if raw_device:
        try:
            device_id = int(raw_device)
        except (TypeError, ValueError):
            return []
    group_key = (request.query_params.get("group") or "").strip() or None
    return resolve_groups("firewall", HA_GROUP_TYPES, device_id=device_id, group_key=group_key)


def _order_rows(rows: list[dict], request) -> list[dict]:
    raw = (request.query_params.get("ordering") or "").strip()
    desc = raw.startswith("-")
    field = raw.lstrip("-")
    if field in {"order", "name", "group_name", "device"}:
        rows.sort(key=lambda row: (row.get(field) or "", row.get("name") or ""), reverse=desc)
    else:
        rows.sort(key=lambda row: (row["group_name"], row.get("order") or 0, row.get("name") or ""))
    return rows


def _paginated(rows: list[dict], request):
    paginator = StandardPagination()
    page = paginator.paginate_queryset(rows, request)
    return paginator.get_paginated_response(page if page is not None else [])


# ---------------------------------------------------------------------------
# 接口
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([AllowAny])
def firewall_policies(request):
    """防火墙主备策略合并列表：
    GET /api/analysis/firewall-groups/policies/?group=&device=&action=&search=&ordering=&page=
    """
    rows = [row for group in _narrow_groups(request) for row in _merge_policies(group)]
    action = (request.query_params.get("action") or "").strip()
    if action:
        rows = [row for row in rows if row["action"].lower() == action.lower()]
    search = (request.query_params.get("search") or "").strip()
    if search:
        needle = search.lower()
        rows = [row for row in rows if needle in _policy_haystack(row)]
    return _paginated(_order_rows(rows, request), request)


@api_view(["GET"])
@permission_classes([AllowAny])
def firewall_nat_rules(request):
    """防火墙主备 NAT 规则合并列表：
    GET /api/analysis/firewall-groups/nat-rules/?group=&device=&nat_type=&search=&ordering=&page=
    """
    rows = [row for group in _narrow_groups(request) for row in _merge_nat_rules(group)]
    nat_type = (request.query_params.get("nat_type") or "").strip()
    if nat_type:
        rows = [row for row in rows if row["nat_type"].lower() == nat_type.lower()]
    search = (request.query_params.get("search") or "").strip()
    if search:
        needle = search.lower()
        rows = [row for row in rows if needle in _nat_haystack(row)]
    return _paginated(_order_rows(rows, request), request)


@api_view(["GET"])
@permission_classes([AllowAny])
def firewall_group_facets(request):
    """过滤下拉选项：GET /api/analysis/firewall-groups/facets/

    ``groups`` 是主备组名 / 单机防火墙名；``actions`` / ``nat_types`` 取自策略与 NAT 的
    去重值。
    """
    groups = [
        {
            "key": group.key,
            "name": group.name,
            "group_id": group.group_id,
            "devices": [device.hostname for device in group.devices],
        }
        for group in resolve_groups("firewall", HA_GROUP_TYPES)
    ]
    actions = sorted({value for value in Policy.objects.values_list("action", flat=True) if value})
    nat_types = sorted({value for value in NatRule.objects.values_list("nat_type", flat=True) if value})
    return Response({"groups": groups, "actions": actions, "nat_types": nat_types})
