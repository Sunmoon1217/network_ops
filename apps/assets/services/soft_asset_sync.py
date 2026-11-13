"""软资产归并（T4）：配置行 → 资产。

两条映射：

- ``GtmWideip``  → ``DomainAsset``（归一键：FQDN 小写去尾点）
- ``LtmVirtualServer`` → ``LoadBalancerService``（归一键：``VIP#port``）

配置行是一设备一行、跨设备重复；归并后一行 = 一个域名 / 一个对外服务，设备退居
「部署位置」多值。**配置行只读**、不动不删；本模块只写 ``ConfigurationItem`` 与两张扩展表。

幂等：重复执行只更新取值变化的资产，不新增、不改 ``ci_id``。已消失的配置不会删除对应资产
（可能已有人工标注），需要时另行处理。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from django.db import connection, transaction
from django.db.models import Count

from assets.models import (
    CIType,
    ConfigurationItem,
    DomainAsset,
    GtmPool,
    GtmServer,
    GtmVServer,
    GtmWideip,
    LoadBalancerService,
    LtmPoolMember,
    LtmVirtualServer,
)

#: 地址与端口的分隔符（IPv6 也用 ``#``，与前端 ``types/lb.ts`` 同约定）
TARGET_SEPARATOR = "#"

#: 归并的事务级咨询锁 key（"SOFT"）：信号（多 worker）与管理命令共用，避免并发
#: ``get_or_create`` 撞唯一约束。项目强绑 PostgreSQL，直接用。
_SYNC_LOCK_KEY = 0x534F4654


@dataclass
class SyncStats:
    """一次归并的增改统计；``skipped`` 是缺归一键（空域名 / 空地址）的配置行数。"""

    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0

    def merge(self, other: SyncStats) -> None:
        self.created += other.created
        self.updated += other.updated
        self.unchanged += other.unchanged
        self.skipped += other.skipped

    def as_dict(self) -> dict[str, int]:
        return {"created": self.created, "updated": self.updated, "unchanged": self.unchanged, "skipped": self.skipped}


def normalize_fqdn(name: str) -> str:
    """域名归一键：去空白与尾点、统一小写（DNS 大小写不敏感）。"""
    return (name or "").strip().rstrip(".").lower()


def lb_asset_key(vip: str, port: str | None) -> str:
    """负载均衡服务归一键：``VIP#port``；端口缺失时只有地址。"""
    address = (vip or "").strip()
    service_port = (port or "").strip()
    return f"{address}{TARGET_SEPARATOR}{service_port}" if service_port else address


def _differs(values) -> bool:
    """一组取值是否不一致（与 ``analysis.api.group_merge._differs`` 同一口径）。"""
    seen = {json.dumps(value, sort_keys=True, default=str) for value in values}
    return len(seen) > 1


def _union(values) -> list:
    """按序并集去重。"""
    union: list = []
    for items in values:
        for item in items or []:
            if item and item not in union:
                union.append(item)
    return union


def _join_ip_port(ip: str | None, port: str | None) -> str:
    if not ip:
        return ""
    service_port = (port or "").strip()
    return f"{ip}{TARGET_SEPARATOR}{service_port}" if service_port else ip


def _parse_member_entry(entry) -> tuple[str, str]:
    """GTM 池成员 → ``(server 名, vserver 名)``。

    兼容入库后的 ``{"server", "vserver"}``、模板产出的 ``{"server_name", "vs_name"}``
    与手工录入的 ``"server:vs"``。（``analysis.api.analysis`` 有同一逻辑，assets 不许
    import analysis，故在此保留一份最小实现。）
    """
    if isinstance(entry, dict):
        server_name = str(entry.get("server_name") or entry.get("server") or "")
        vs_name = str(entry.get("vs_name") or entry.get("vserver") or entry.get("virtual_server") or "")
        if not server_name or not vs_name:
            left, _, right = str(entry.get("name") or "").partition(":")
            server_name = server_name or left
            vs_name = vs_name or right
        return server_name, vs_name
    server_name, _, vs_name = str(entry or "").partition(":")
    return server_name, vs_name


@dataclass
class _DomainGroup:
    fqdn: str
    rtypes: list[str] = field(default_factory=list)
    lb_modes: list[str] = field(default_factory=list)
    ttls: list[int] = field(default_factory=list)
    pools: list[str] = field(default_factory=list)
    fallback_ips: list[str] = field(default_factory=list)
    vips: list[str] = field(default_factory=list)
    devices: list[str] = field(default_factory=list)


@dataclass
class _ServiceGroup:
    asset_key: str
    vip: str
    port: str
    protocols: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    pools: list[str] = field(default_factory=list)
    profiles: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    devices: list[str] = field(default_factory=list)
    #: device_id → 该设备上被这个 VIP 引用的池名（成员数按设备算，避免主备重复计数）
    pools_by_device: dict[int, list[str]] = field(default_factory=dict)


def _vserver_index(device_ids: set[int]) -> dict[tuple[int, str, str], GtmVServer]:
    """``(device_id, server 名, vs 名) → GtmVServer``：成员只存名字，IP 在 vs 上。"""
    server_names = dict(GtmServer.objects.filter(device_id__in=device_ids).values_list("id", "name"))
    index: dict[tuple[int, str, str], GtmVServer] = {}
    for vserver in GtmVServer.objects.filter(device_id__in=device_ids).select_related("server"):
        index[(vserver.device_id, server_names.get(vserver.server_id) or vserver.server.name, vserver.name)] = vserver
    return index


def _build_domain_groups(stats: SyncStats) -> dict[str, _DomainGroup]:
    wideips = list(GtmWideip.objects.select_related("device").order_by("device__hostname", "name", "rtype", "pk"))
    device_ids = {wideip.device_id for wideip in wideips}
    pool_names = {name for wideip in wideips for name in wideip.pool_names}
    pools: dict[tuple[int, str], GtmPool] = {}
    if pool_names:
        pools = {(pool.device_id, pool.name): pool for pool in GtmPool.objects.filter(device_id__in=device_ids, name__in=pool_names)}
    vservers = _vserver_index(device_ids)

    groups: dict[str, _DomainGroup] = {}
    for wideip in wideips:
        fqdn = normalize_fqdn(wideip.name)
        if not fqdn:
            stats.skipped += 1
            continue
        group = groups.setdefault(fqdn, _DomainGroup(fqdn=fqdn))
        group.rtypes.append(wideip.rtype)
        group.lb_modes.append(wideip.lb_mode)
        if wideip.device.hostname not in group.devices:
            group.devices.append(wideip.device.hostname)

        for pool_name in wideip.pool_names:
            group.pools.append(pool_name)
            pool = pools.get((wideip.device_id, pool_name))
            if pool is None:
                continue
            group.ttls.append(pool.ttl)
            if pool.fallback_ip:
                group.fallback_ips.append(str(pool.fallback_ip))
            for entry in pool.members or []:
                server_name, vs_name = _parse_member_entry(entry)
                target = vservers.get((wideip.device_id, server_name, vs_name))
                if target and target.ip_address:
                    group.vips.append(_join_ip_port(str(target.ip_address), target.port))
    return groups


def _sync_domain_group(group: _DomainGroup, stats: SyncStats) -> None:
    conflict_fields = []
    if _differs(group.lb_modes):
        conflict_fields.append("lb_mode")
    if _differs(group.ttls):
        conflict_fields.append("ttl")

    values = {
        "rtypes": _union([group.rtypes]),
        "ttl": group.ttls[0] if group.ttls else None,
        "lb_mode": group.lb_modes[0] if group.lb_modes else "",
        "pools": _union([group.pools]),
        "fallback_ips": _union([group.fallback_ips]),
        "vips": _union([group.vips]),
        "devices": group.devices,
        "inconsistent": bool(conflict_fields),
        "conflict_fields": conflict_fields,
    }

    asset = DomainAsset.objects.filter(fqdn=group.fqdn).select_related("ci").first()
    if asset is None:
        ci = ConfigurationItem.objects.create(ci_type=CIType.DOMAIN, name=group.fqdn)
        DomainAsset.objects.create(ci=ci, fqdn=group.fqdn, **values)
        stats.created += 1
        return

    changed = any(getattr(asset, name) != value for name, value in values.items())
    if not changed:
        if asset.ci.name != group.fqdn:
            asset.ci.name = group.fqdn
            asset.ci.save(update_fields=["name", "updated_at"])
        stats.unchanged += 1
        return
    for name, value in values.items():
        setattr(asset, name, value)
    asset.save()
    stats.updated += 1


@transaction.atomic
def sync_domain_assets() -> SyncStats:
    """``GtmWideip`` → ``DomainAsset``：按 FQDN 跨设备归并。"""
    stats = SyncStats()
    for group in _build_domain_groups(stats).values():
        _sync_domain_group(group, stats)
    return stats


def _member_counts(device_ids: set[int]) -> dict[tuple[int, str], int]:
    rows = LtmPoolMember.objects.filter(device_id__in=device_ids).values("device_id", "pool_name").annotate(total=Count("id"))
    return {(row["device_id"], row["pool_name"]): row["total"] for row in rows}


def _build_service_groups(stats: SyncStats) -> tuple[dict[str, _ServiceGroup], dict[tuple[int, str], int]]:
    vservers = list(LtmVirtualServer.objects.select_related("device").order_by("device__hostname", "name", "pk"))
    device_ids = {vserver.device_id for vserver in vservers}
    member_counts = _member_counts(device_ids)

    groups: dict[str, _ServiceGroup] = {}
    for vserver in vservers:
        vip = (vserver.vs_address or "").strip()
        if not vip:
            # 透明 / 无地址的 VS 不构成对外服务资产（跨设备也无可归并的键）
            stats.skipped += 1
            continue
        port = (vserver.vs_port or "").strip()
        key = lb_asset_key(vip, port)
        group = groups.setdefault(key, _ServiceGroup(asset_key=key, vip=vip, port=port))
        group.protocols.append(vserver.protocol or "")
        group.statuses.append(vserver.status or "")
        group.profiles.extend(vserver.profiles or [])
        group.rules.extend(vserver.rules or [])
        if vserver.device.hostname not in group.devices:
            group.devices.append(vserver.device.hostname)
        if vserver.pool:
            group.pools.append(vserver.pool)
            group.pools_by_device.setdefault(vserver.device_id, []).append(vserver.pool)
    return groups, member_counts


def _service_member_count(group: _ServiceGroup, member_counts: dict[tuple[int, str], int]) -> int:
    """一台设备上一个 VIP 引多个池时求和，再取各设备最大值——主备是同一份配置，不能相加。"""
    per_device = [sum(member_counts.get((device_id, pool), 0) for pool in pools) for device_id, pools in group.pools_by_device.items()]
    return max(per_device, default=0)


def _sync_service_group(group: _ServiceGroup, member_counts: dict[tuple[int, str], int], stats: SyncStats) -> None:
    conflict_fields = []
    if _differs([protocol for protocol in group.protocols if protocol]):
        conflict_fields.append("protocol")
    if _differs([status for status in group.statuses if status]):
        conflict_fields.append("status")

    values = {
        "vip": group.vip,
        "port": group.port,
        "protocol": group.protocols[0] if group.protocols else "",
        "pools": _union([group.pools]),
        "member_count": _service_member_count(group, member_counts),
        "profiles": _union([group.profiles]),
        "rules": _union([group.rules]),
        "devices": group.devices,
        "status": group.statuses[0] if group.statuses else "",
        "inconsistent": bool(conflict_fields),
        "conflict_fields": conflict_fields,
    }

    asset = LoadBalancerService.objects.filter(asset_key=group.asset_key).select_related("ci").first()
    if asset is None:
        ci = ConfigurationItem.objects.create(ci_type=CIType.LOAD_BALANCER_SERVICE, name=group.asset_key)
        LoadBalancerService.objects.create(ci=ci, asset_key=group.asset_key, **values)
        stats.created += 1
        return

    changed = any(getattr(asset, name) != value for name, value in values.items())
    if not changed:
        if asset.ci.name != group.asset_key:
            asset.ci.name = group.asset_key
            asset.ci.save(update_fields=["name", "updated_at"])
        stats.unchanged += 1
        return
    for name, value in values.items():
        setattr(asset, name, value)
    asset.save()
    stats.updated += 1


@transaction.atomic
def sync_load_balancer_services() -> SyncStats:
    """``LtmVirtualServer`` → ``LoadBalancerService``：按 ``VIP#port`` 跨设备归并。"""
    stats = SyncStats()
    groups, member_counts = _build_service_groups(stats)
    for group in groups.values():
        _sync_service_group(group, member_counts, stats)
    return stats


@transaction.atomic
def sync_soft_assets(asset_type: str = "all") -> SyncStats:
    """``asset_type``：``all`` / ``domain`` / ``lb``。

    整个归并在一把事务级咨询锁里执行：Celery 多 worker 与管理命令并发时串行，
    后到者会看到前者的结果，``get_or_create`` 不会撞唯一约束。
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_SYNC_LOCK_KEY])

    stats = SyncStats()
    if asset_type in ("all", "domain"):
        stats.merge(sync_domain_assets())
    if asset_type in ("all", "lb"):
        stats.merge(sync_load_balancer_services())
    return stats
