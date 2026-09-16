"""负载均衡数据保存器 (LTM + GTM)"""
from logging import getLogger
from typing import Any

from .base import BaseSaver

logger = getLogger(__name__)


def _as_list(value: Any) -> list:
    """统一成列表。

    TTP 只解析到一条记录时给出的是 dict 而不是 list，直接遍历会拿到 key 字符串，
    导致 saver 里 pool.get(...) 抛 AttributeError。
    """
    if not value:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return value
    return []


class LBVirtualServerSaver(BaseSaver):
    device_types = ["loadbalancer"]
    keys = ["virtuals"]

    def save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import LtmVirtualServer

        virtuals = _as_list(parsed_data.get("virtuals"))
        if not virtuals:
            return (0, 0)

        created, updated = 0, 0
        for vs in virtuals:
            name = vs.get("name")
            if not name:
                continue
            snat = vs.get("snat") if isinstance(vs.get("snat"), dict) else {}
            _, is_created = LtmVirtualServer.objects.update_or_create(
                device=device, name=name,
                defaults={
                    "vs_address": vs.get("vs_address", ""),
                    "vs_port": vs.get("vs_port", ""),
                    "mask": vs.get("mask"),
                    "protocol": vs.get("protocol", ""),
                    "status": vs.get("status", "enabled"),
                    "source": vs.get("source"),
                    "pool": vs.get("pool", ""),
                    # 新模板把 snat 收进 source-address-translation 子块，这里兼容旧格式
                    "snat_type": snat.get("snat_type", vs.get("snat_type", "")),
                    "snat_pool": snat.get("snat_pool", vs.get("snat_pool")),
                    "persist": self._extract_persist(vs.get("persist")),
                    "profiles": self._normalize_list(vs.get("profiles")),
                    "rules": self._normalize_list(vs.get("rules")),
                },
            )
            created += 1 if is_created else 0
            updated += 0 if is_created else 1
        return (created, updated)

    def _normalize_list(self, value: Any) -> list:
        if not value:
            return []
        if isinstance(value, dict):
            return [value.get("name", "")]
        if isinstance(value, list):
            return [item.get("name", str(item)) if isinstance(item, dict) else str(item) for item in value]
        return [str(value)]

    def _extract_persist(self, value: Any) -> str | None:
        if not value:
            return None
        return value.get("name") if isinstance(value, dict) else str(value)


class LBPoolSaver(BaseSaver):
    device_types = ["loadbalancer"]
    keys = ["pools"]

    def save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import LtmPool, LtmPoolMember

        pools = _as_list(parsed_data.get("pools"))
        if not pools:
            return (0, 0)

        created, updated = 0, 0
        for pool in pools:
            name = pool.get("name")
            if not name:
                continue
            _, is_created = LtmPool.objects.update_or_create(
                device=device, name=name,
                defaults={
                    "mode": pool.get("mode", pool.get("load-balancing-mode", "")),
                    "monitors": pool.get("monitors", pool.get("monitor", [])),
                },
            )
            created += 1 if is_created else 0
            updated += 0 if is_created else 1
            members = _as_list(pool.get("members"))
            if members:
                LtmPoolMember.objects.filter(pool_name=name).delete()
                LtmPoolMember.objects.bulk_create([
                    LtmPoolMember(
                        pool_name=name,
                        name=m.get("name", ""),
                        address=m.get("address", ""),
                        port=str(m.get("port") or ""),
                    )
                    for m in members if m.get("name")
                ])
        return (created, updated)


class LBSnatSaver(BaseSaver):
    device_types = ["loadbalancer"]
    keys = ["snat_pools", "snat"]

    def save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import LtmSNAT

        snats = parsed_data.get("snat_pools", parsed_data.get("snat", []))
        if not snats:
            return (0, 0)

        created, updated = 0, 0
        for snat in snats:
            name = snat.get("name")
            if not name:
                continue
            _, is_created = LtmSNAT.objects.update_or_create(
                device=device, name=name,
                defaults={"address": snat.get("address", "")},
            )
            created += 1 if is_created else 0
            updated += 0 if is_created else 1
        return (created, updated)


class GTMWideipSaver(BaseSaver):
    device_types = ["loadbalancer"]
    keys = ["wideips"]

    def save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import GtmWideip

        wideips = _as_list(parsed_data.get("wideips"))
        if not wideips:
            return (0, 0)

        created, updated = 0, 0
        for w in wideips:
            name = w.get("wideip_name", w.get("name"))
            if not name:
                continue
            pools_raw = w.get("pools", [])
            if isinstance(pools_raw, list):
                pools = [p.get("pool_name", p.get("name", "")) if isinstance(p, dict) else str(p) for p in pools_raw]
            elif isinstance(pools_raw, str):
                pools = [pools_raw]
            else:
                pools = []
            _, is_created = GtmWideip.objects.update_or_create(
                device=device, name=name,
                defaults={"rtype": w.get("rtype", ""), "lb_mode": w.get("lb_mode", ""), "pools": pools},
            )
            created += 1 if is_created else 0
            updated += 0 if is_created else 1
        return (created, updated)
