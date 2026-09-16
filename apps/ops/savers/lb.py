"""负载均衡数据保存器 (LTM + GTM)"""

from logging import getLogger
from typing import Any

from .base import BaseSaver, as_list

logger = getLogger(__name__)


class LBVirtualServerSaver(BaseSaver):
    """虚拟服务器保存器。

    同一份 ``virtuals`` 产出里还嵌着 profiles / rules / persist，这三个模型
    （``LtmProfile`` / ``LtmIRule`` / ``LtmPersist``）是**设备级清单**、没有指向
    virtual server 的外键，所以在同一个 Saver 里一并落库，来源记进 ``raw``。
    """

    device_types = ["slb"]
    keys = ["virtuals"]

    def save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import LtmVirtualServer

        virtuals = as_list(parsed_data.get("virtuals"))
        if not virtuals:
            return (0, 0)

        created, updated = 0, 0
        for vs in virtuals:
            name = vs.get("name")
            if not name:
                continue
            snat = vs.get("snat") if isinstance(vs.get("snat"), dict) else {}
            _, is_created = LtmVirtualServer.objects.update_or_create(
                device=device,
                name=name,
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
                    "profiles": self._flatten_names(vs.get("profiles")),
                    "rules": self._flatten_names(vs.get("rules")),
                },
            )
            created += 1 if is_created else 0
            updated += 0 if is_created else 1

            for sub_created, sub_updated in (
                self._save_profiles(device, vs.get("profiles"), name),
                self._save_rules(device, vs.get("rules"), name),
                self._save_persist(device, vs.get("persist"), name),
            ):
                created += sub_created
                updated += sub_updated
        return (created, updated)

    def _save_profiles(self, device, value, vs_name: str) -> tuple[int, int]:
        from assets.models import LtmProfile
        from assets.serializers.views import LtmProfileSerializer

        created, updated = 0, 0
        for raw in self._named_entries(value):
            profile_name = raw.get("name")
            is_new = self.upsert(
                LtmProfileSerializer,
                LtmProfile,
                device,
                {"name": profile_name},
                {
                    "name": profile_name,
                    "type": self._basename(profile_name),
                    "raw": {**raw, "virtual_server": vs_name},
                },
            )
            created += 1 if is_new else 0
            updated += 0 if is_new else 1
        return (created, updated)

    def _save_rules(self, device, value, vs_name: str) -> tuple[int, int]:
        from assets.models import LtmIRule
        from assets.serializers.views import LtmIRuleSerializer

        created, updated = 0, 0
        for rule_name in self._flatten_names(value):
            is_new = self.upsert(
                LtmIRuleSerializer,
                LtmIRule,
                device,
                {"name": rule_name},
                {"name": rule_name, "raw": {"name": rule_name, "virtual_server": vs_name}},
            )
            created += 1 if is_new else 0
            updated += 0 if is_new else 1
        return (created, updated)

    def _save_persist(self, device, value, vs_name: str) -> tuple[int, int]:
        from assets.models import LtmPersist
        from assets.serializers.views import LtmPersistSerializer

        created, updated = 0, 0
        for raw in self._named_entries(value):
            persist_name = raw.get("name")
            is_new = self.upsert(
                LtmPersistSerializer,
                LtmPersist,
                device,
                {"name": persist_name},
                {
                    "name": persist_name,
                    "type": self._basename(persist_name),
                    "raw": {**raw, "virtual_server": vs_name},
                },
            )
            created += 1 if is_new else 0
            updated += 0 if is_new else 1
        return (created, updated)

    def _flatten_names(self, value: Any) -> list[str]:
        """把 profiles / rules / persist 的多种产出形态拉平成名字列表。

        实测三种形态（TTP 单条命中会给 dict 而不是 list）::

            profiles -> [{"name": "/Common/http"}, ...]
            rules    -> {"name": ["/Common/irule_redirect"]}
            persist  -> {"name": "/Common/cookie"}
        """
        names = []
        for item in as_list(value):
            name = item.get("name") if isinstance(item, dict) else item
            candidates = [name] if isinstance(name, str) else as_list(name)
            names.extend(str(candidate) for candidate in candidates if candidate)
        return names

    def _named_entries(self, value: Any) -> list[dict]:
        """取出带有 name 的记录体，供 raw 字段留档（兼容 dict / list / 裸字符串）"""
        entries = []
        for item in as_list(value):
            if isinstance(item, dict) and item.get("name"):
                entries.append(item)
            elif isinstance(item, str) and item:
                entries.append({"name": item})
        return entries

    def _basename(self, name: str) -> str:
        """``/Common/http`` -> ``http``，用作 LtmProfile.type / LtmPersist.type"""
        return str(name).rstrip("/").rsplit("/", 1)[-1] or "unknown"

    def _extract_persist(self, value: Any) -> str | None:
        if not value:
            return None
        return value.get("name") if isinstance(value, dict) else str(value)


class LBPoolSaver(BaseSaver):
    device_types = ["slb"]
    keys = ["pools"]

    def save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import LtmPool, LtmPoolMember

        pools = as_list(parsed_data.get("pools"))
        if not pools:
            return (0, 0)

        created, updated = 0, 0
        for pool in pools:
            name = pool.get("name")
            if not name:
                continue
            _, is_created = LtmPool.objects.update_or_create(
                device=device,
                name=name,
                defaults={
                    "mode": pool.get("mode", pool.get("load-balancing-mode", "")),
                    "monitors": pool.get("monitors", pool.get("monitor", [])),
                },
            )
            created += 1 if is_created else 0
            updated += 0 if is_created else 1
            members = as_list(pool.get("members"))
            if members:
                LtmPoolMember.objects.filter(pool_name=name).delete()
                LtmPoolMember.objects.bulk_create(
                    [
                        LtmPoolMember(
                            pool_name=name,
                            name=m.get("name", ""),
                            address=m.get("address", ""),
                            port=str(m.get("port") or ""),
                        )
                        for m in members
                        if m.get("name")
                    ]
                )
        return (created, updated)


class LBSnatSaver(BaseSaver):
    device_types = ["slb"]
    keys = ["snat_pools", "snat"]

    def save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import LtmSNAT

        snats = as_list(parsed_data.get("snat_pools") or parsed_data.get("snat"))
        if not snats:
            return (0, 0)

        created, updated = 0, 0
        for snat in snats:
            name = snat.get("name")
            if not name:
                continue
            _, is_created = LtmSNAT.objects.update_or_create(
                device=device,
                name=name,
                defaults={"address": snat.get("address", "")},
            )
            created += 1 if is_created else 0
            updated += 0 if is_created else 1
        return (created, updated)


class GTMWideipSaver(BaseSaver):
    device_types = ["gslb"]
    keys = ["wideips"]

    def save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import GtmWideip

        wideips = as_list(parsed_data.get("wideips"))
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
                device=device,
                name=name,
                defaults={
                    # f5_gtm.ttp 产出的是 wideip_type / wideip_lbmode，
                    # 原先直接取 rtype / lb_mode，这两个字段永远是空
                    "rtype": w.get("wideip_type", w.get("rtype", "")),
                    "lb_mode": w.get("wideip_lbmode", w.get("lb_mode", "")),
                    "pools": pools,
                },
            )
            created += 1 if is_created else 0
            updated += 0 if is_created else 1
        return (created, updated)


class GtmDatacenterSaver(BaseSaver):
    """GTM 数据中心保存器。"""

    device_types = ["gslb"]
    keys = ["datacenters"]

    def save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import GtmDatacenter
        from assets.serializers.views import GtmDatacenterSerializer

        created, updated = 0, 0
        for dc in as_list(parsed_data.get("datacenters")):
            name = dc.get("name")
            if not name:
                continue
            is_new = self.upsert(GtmDatacenterSerializer, GtmDatacenter, device, {"name": name}, {"name": name})
            created += 1 if is_new else 0
            updated += 0 if is_new else 1
        return (created, updated)


class GtmServerSaver(BaseSaver):
    """GTM 服务器保存器，连带保存其 virtual-servers 子块。"""

    device_types = ["gslb"]
    keys = ["servers"]

    def save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import GtmServer, GtmVServer
        from assets.serializers.views import GtmServerSerializer, GtmVServerSerializer

        created, updated = 0, 0
        for srv in as_list(parsed_data.get("servers")):
            name = srv.get("server_name")
            if not name:
                continue
            is_new = self.upsert(
                GtmServerSerializer,
                GtmServer,
                device,
                {"name": name},
                {
                    "name": name,
                    "datacenter": srv.get("datacenter") or "",
                    "monitor": srv.get("server_monitor") or "",
                    "server_type": srv.get("server_type") or "",
                },
            )
            created += 1 if is_new else 0
            updated += 0 if is_new else 1

            # virtual-servers 是 servers 的子 group：一个 server 下挂多个 vserver
            server = GtmServer.objects.filter(device=device, name=name).first()
            for vs in as_list(srv.get("virtual_servers")):
                vs_name = vs.get("vs_name")
                if not vs_name:
                    continue
                is_new_vs = self.upsert(
                    GtmVServerSerializer,
                    GtmVServer,
                    device,
                    {"server": server, "name": vs_name},
                    {
                        "server": server.pk,
                        "name": vs_name,
                        "ip_address": vs.get("vs_address") or None,
                        "port": str(vs.get("vs_port") or ""),
                        "monitor": vs.get("vs_monitor") or "",
                    },
                )
                created += 1 if is_new_vs else 0
                updated += 0 if is_new_vs else 1
        return (created, updated)


class GtmPoolSaver(BaseSaver):
    """GTM 池保存器，成员落 JSON 字段。"""

    device_types = ["gslb"]
    keys = ["pools"]

    def save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import GtmPool
        from assets.serializers.views import GtmPoolSerializer

        created, updated = 0, 0
        for pool in as_list(parsed_data.get("pools")):
            name = pool.get("pool_name")
            if not name:
                continue
            monitor = pool.get("pool_monitor")
            payload = {
                "name": name,
                "lb_mode": pool.get("preferred") or "round-robin",
                "alternate_mode": pool.get("alternate-mode") or "round-robin",
                "fallback_mode": pool.get("fallback-mode") or "return-to-dns",
                "ttl": self._safe_int(pool.get("ttl")) or 30,
                "monitor": [monitor] if monitor else [],
                "members": self._normalize_members(pool),
                "is_active": pool.get("pool_status", "enabled") != "disabled",
            }
            # fallback_ip 是 GenericIPAddressField，空串会被序列化器判为非法
            fallback_ip = pool.get("fallback-ip")
            if fallback_ip:
                payload["fallback_ip"] = fallback_ip
            is_new = self.upsert(GtmPoolSerializer, GtmPool, device, {"name": name}, payload)
            created += 1 if is_new else 0
            updated += 0 if is_new else 1
        return (created, updated)

    def _normalize_members(self, pool: dict) -> list[dict]:
        members = []
        for member in as_list(pool.get("members")):
            server = member.get("server_name")
            if not server:
                continue
            members.append(
                {
                    "server": server,
                    "vserver": member.get("vs_name", ""),
                    "status": member.get("member_status", "enabled"),
                    "order": self._safe_int(member.get("member_order")) or 0,
                    "ratio": self._safe_int(member.get("member_ratio")) or 1,
                    "monitor": member.get("member_monitor", ""),
                }
            )
        return members
