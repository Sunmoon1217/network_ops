"""软资产「写」这一半：候选值 → CI 台账 + 两张扩展表（**只写 assets 自己的表**）。

输入是 ``configs.services.soft_asset_builder`` 算好的 draft：``kind`` + 归一键 ``key`` +
扩展表字段 ``values``。本模块不认识 configs——它只按 ``kind`` 查表往前写，
用 ``Protocol`` 做结构化类型，连 import 都不需要。

幂等：重复执行只更新取值变化的资产，不新增、不改 ``ci_id``。已消失的配置不会删除对应
资产（可能已有人工标注），需要时另行处理。

为什么拆成两半：拆分前这个模块同时读 configs 的表、写 assets 的表，是整库唯一横跨两域
做读写的地方（``assets → configs`` 是依赖矩阵禁止的方向）。现在 assets 只提供写入能力，
编排（先算后写、同一事务）在 configs 侧。
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
