"""软资产「写」这一半：候选值 → CI 台账 + 两张扩展表（只写 assets 自己的表）。

输入是 configs 侧算好的 draft；本模块不认识 configs，按 ``kind`` 查表写入。
幂等，已消失的配置不删对应资产。拆分缘由见 handbook/assets.md「归并链路」。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from assets.models import CIType, ConfigurationItem, DomainAsset, LoadBalancerService


class SoftAssetDraftLike(Protocol):
    """configs 侧 draft 的结构（只用只读属性，冻结 dataclass 即可满足）。"""

    @property
    def kind(self) -> str: ...

    @property
    def key(self) -> str: ...

    @property
    def values(self) -> dict: ...


#: kind → (CI 类型, 扩展表模型, 归一键字段名)
_SPEC = {
    "domain": (CIType.DOMAIN, DomainAsset, "fqdn"),
    "lb_service": (CIType.LOAD_BALANCER_SERVICE, LoadBalancerService, "asset_key"),
}


@dataclass
class SyncStats:
    """一次归并的增改统计；``skipped`` 由 configs 侧的计算阶段填入。"""

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


def _apply_draft(draft: SoftAssetDraftLike, stats: SyncStats) -> None:
    ci_type, model, key_field = _SPEC[draft.kind]
    values = draft.values

    asset = model.objects.filter(**{key_field: draft.key}).select_related("ci").first()
    if asset is None:
        ci = ConfigurationItem.objects.create(ci_type=ci_type, name=draft.key)
        model.objects.create(ci=ci, **{key_field: draft.key}, **values)
        stats.created += 1
        return

    changed = any(getattr(asset, name) != value for name, value in values.items())
    if not changed:
        if asset.ci.name != draft.key:
            asset.ci.name = draft.key
            asset.ci.save(update_fields=["name", "updated_at"])
        stats.unchanged += 1
        return
    for name, value in values.items():
        setattr(asset, name, value)
    asset.save()
    stats.updated += 1


def apply_soft_assets(drafts: Sequence[SoftAssetDraftLike]) -> SyncStats:
    """把候选值写进 CI 台账与扩展表（调用方负责事务与并发锁）。"""
    stats = SyncStats()
    for draft in drafts:
        _apply_draft(draft, stats)
    return stats
