"""存量资产登记（T4）：`Device` / `IPAddress` / `Subnet` → `ConfigurationItem` + `CIObjectLink`。

幂等：按 `(source_type, source_id)` 找已有映射；只更新名字变化的 CI，`ci_id` 保持不变。
批量：CI 与映射都走 bulk_create / bulk_update，IPAM 万级也能一次跑完。

并发：与软资产归并共用「事务级咨询锁」的做法（`pg_advisory_xact_lock`，项目强绑 PostgreSQL），
多个进程同时跑命令时串行化，避免 `get_or_create` 撞唯一约束。
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import connection, transaction
from django.utils import timezone

from assets.models import CIObjectLink, CIType, ConfigurationItem, Device, IPAddress, Subnet
from assets.models.ci import _new_ci_id

#: 登记锁（"REGI"）；与软资产的 "SOFT" 分开，两件事可以并行
_REGISTRY_LOCK_KEY = 0x52454749

#: 来源类型 → (模型, 取名字段)；名字字段都是必填且唯一，登记时直接当 CI 名称
_SOURCES = {
    CIType.DEVICE: (Device, "hostname"),
    CIType.IP_ADDRESS: (IPAddress, "ip_address"),
    CIType.SUBNET: (Subnet, "network"),
}


@dataclass
class RegistryStats:
    """一次登记的增改统计。"""

    created: int = 0
    updated: int = 0
    unchanged: int = 0

    def merge(self, other: RegistryStats) -> None:
        self.created += other.created
        self.updated += other.updated
        self.unchanged += other.unchanged

    def as_dict(self) -> dict[str, int]:
        return {"created": self.created, "updated": self.updated, "unchanged": self.unchanged}


def register_existing_assets(kinds: list[str] | None = None, dry_run: bool = False) -> dict[str, RegistryStats]:
    """把所有（或指定类型的）存量资产登记进 CI 主表；返回按类型分组的统计。

    ``kinds`` 取 `CIType` 里的三个值（device / ip_address / subnet），默认全做。
    ``dry_run`` 只统计、不写库。
    """
    wanted = list(kinds) if kinds else list(_SOURCES)
    unknown = [kind for kind in wanted if kind not in _SOURCES]
    if unknown:
        raise ValueError(f"不支持的存量资产类型：{unknown}；可选 {sorted(_SOURCES)}")

    with transaction.atomic():
        if not dry_run:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_REGISTRY_LOCK_KEY])
        return {kind: _register_kind(kind, *_SOURCES[kind], dry_run=dry_run) for kind in wanted}


def _register_kind(kind: str, model, name_field: str, dry_run: bool) -> RegistryStats:
    """登记单一类型；先读已有映射再决定新增 / 改名，最后批量落库。"""
    stats = RegistryStats()
    existing = {link.source_id: link for link in CIObjectLink.objects.filter(source_type=kind).select_related("ci")}

    new_cis: list[ConfigurationItem] = []
    new_links: list[CIObjectLink] = []
    changed_cis: list[ConfigurationItem] = []

    for obj in model.objects.all().only("pk", name_field).order_by("pk").iterator(chunk_size=2000):
        name = str(getattr(obj, name_field))
        link = existing.get(obj.pk)
        if link is None:
            ci = ConfigurationItem(ci_id=_new_ci_id(), ci_type=kind, name=name)
            new_cis.append(ci)
            new_links.append(CIObjectLink(ci=ci, source_type=kind, source_id=obj.pk))
            stats.created += 1
        elif link.ci.name != name:
            link.ci.name = name
            changed_cis.append(link.ci)
            stats.updated += 1
        else:
            stats.unchanged += 1

    if dry_run:
        return stats

    if new_cis:
        ConfigurationItem.objects.bulk_create(new_cis, batch_size=500)
        CIObjectLink.objects.bulk_create(new_links, batch_size=500)
    if changed_cis:
        now = timezone.now()
        for ci in changed_cis:
            ci.updated_at = now
        ConfigurationItem.objects.bulk_update(changed_cis, ["name", "updated_at"], batch_size=500)
    return stats
