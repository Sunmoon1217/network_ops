"""负载均衡数据保存器 (LTM + GTM)"""

from logging import getLogger
from typing import Any

from .base import BaseSaver, as_list, status_enabled

logger = getLogger(__name__)


class LBVirtualServerSaver(BaseSaver):
    """虚拟服务器保存器。

    同一份 ``virtuals`` 产出里还嵌着 profiles / rules / persist，这三个模型
    （``LtmProfile`` / ``LtmIRule`` / ``LtmPersist``）是**设备级清单**、没有指向
    virtual server 的外键，所以在同一个 Saver 里一并落库，来源记进 ``raw``。
    """

    device_types = ["slb"]
    keys = ["virtuals"]
    model_paths = [
        "assets.models.LtmVirtualServer",
        "assets.models.LtmProfile",
        "assets.models.LtmIRule",
        "assets.models.LtmPersist",
    ]

    def _save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import LtmIRule, LtmPersist, LtmProfile, LtmVirtualServer
        from assets.serializers.views import LtmIRuleSerializer, LtmPersistSerializer, LtmProfileSerializer

        virtuals = as_list(parsed_data.get("virtuals"))
        if not virtuals:
            return (0, 0)

        vs_rows = []
        # profiles / rules / persist 是设备级清单：同一个名字被多个 virtual 引用时只留
        # 一条，按写入顺序后来者覆盖（与逐条 upsert 的语义一致，raw 记最后一次来源）
        profiles: dict[str, dict] = {}
        rules: dict[str, dict] = {}
        persists: dict[str, dict] = {}

        for vs in virtuals:
            name = self._leaf(vs.get("name"))
            if not name:
                continue
            snat = vs.get("snat") if isinstance(vs.get("snat"), dict) else {}
            vs_rows.append(
                {
                    "name": name,
                    "vs_address": vs.get("vs_address", ""),
                    "vs_port": vs.get("vs_port", ""),
                    "mask": vs.get("mask"),
                    "protocol": vs.get("protocol", ""),
                    # 双轨：新模板 enabled 0/1；手工 payload / 旧 config_json 给 status str
                    "status": "enabled" if status_enabled(vs, "status") else "disabled",
                    "source": vs.get("source"),
                    "pool": self._leaf(vs.get("pool")),
                    # 新模板把 snat 收进 source-address-translation 子块，这里兼容旧格式
                    "snat_type": snat.get("snat_type", vs.get("snat_type", "")),
                    "snat_pool": self._leaf(snat.get("snat_pool") or vs.get("snat_pool")),
                    "persist": self._extract_persist(vs.get("persist")),
                    "profiles": self._flatten_names(vs.get("profiles")),
                    "rules": self._flatten_names(vs.get("rules")),
                }
            )

            for raw in self._named_entries(vs.get("profiles")):
                profile_name = self._leaf(raw.get("name"))
                if profile_name:
                    profiles[profile_name] = {
                        "name": profile_name,
                        "type": self._basename(profile_name),
                        "raw": {**raw, "virtual_server": name},
                    }
            for rule_name in self._flatten_names(vs.get("rules")):
                rules[rule_name] = {
                    "name": rule_name,
                    "raw": {"name": rule_name, "virtual_server": name},
                }
            for raw in self._named_entries(vs.get("persist")):
                persist_name = self._leaf(raw.get("name"))
                if persist_name:
                    persists[persist_name] = {
                        "name": persist_name,
                        "type": self._basename(persist_name),
                        "raw": {**raw, "virtual_server": name},
                    }

        created, updated = self.bulk_upsert(LtmVirtualServer, device, vs_rows, key_fields=("name",))
        for model, rows, serializer_cls in (
            (LtmProfile, list(profiles.values()), LtmProfileSerializer),
            (LtmIRule, list(rules.values()), LtmIRuleSerializer),
            (LtmPersist, list(persists.values()), LtmPersistSerializer),
        ):
            sub_created, sub_updated = self.bulk_upsert(
                model, device, rows, key_fields=("name",), serializer_cls=serializer_cls
            )
            created += sub_created
            updated += sub_updated
        return (created, updated)

    def _flatten_names(self, value: Any) -> list[str]:
        """把 profiles / rules / persist 的多种产出形态拉平成名字列表。

        实测三种形态（TTP 单条命中会给 dict 而不是 list）::

            profiles -> [{"name": "/Common/http"}, ...]
            rules    -> {"name": ["/Common/irule_redirect"]}
            persist  -> {"name": "/Common/cookie"}
        """
        names: list[str] = []
        for item in as_list(value):
            name = item.get("name") if isinstance(item, dict) else item
            candidates = [name] if isinstance(name, str) else as_list(name)
            names.extend(self._leaf(candidate) for candidate in candidates if candidate)
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
        name = value.get("name") if isinstance(value, dict) else value
        return self._leaf(name) or None


class LBPoolSaver(BaseSaver):
    device_types = ["slb"]
    keys = ["pools"]
    model_paths = ["assets.models.LtmPool", "assets.models.LtmPoolMember"]

    def _save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import LtmPool, LtmPoolMember

        pools = as_list(parsed_data.get("pools"))
        if not pools:
            return (0, 0)

        pool_rows = []
        member_rows = []
        # 成员没有独立的自然键，只能「先清后建」。清理范围按「设备 + 池名」圈定：
        # 只按 pool_name 全局匹配会误删其他设备上同名池的成员。
        # 池在配置里出现过就以配置为准，成员清空也要把旧记录删掉。
        touched_pool_names: list[str] = []

        for pool in pools:
            name = self._leaf(pool.get("name"))
            if not name:
                continue
            touched_pool_names.append(name)
            pool_rows.append(
                {
                    "name": name,
                    "mode": pool.get("mode", pool.get("load-balancing-mode", "")),
                    "monitors": self._leaf_list(pool.get("monitors") or pool.get("monitor")),
                }
            )

            seen: set[tuple[str, str]] = set()
            for member in as_list(pool.get("members")):
                if not isinstance(member, dict):
                    continue
                member_name = self._leaf(member.get("name"))
                if not member_name:
                    continue
                port = str(member.get("port") or "")
                # 同一节点可能在多个端口上做成员，唯一键是
                # (device, pool_name, name, port)，同组重复要先去掉
                if (member_name, port) in seen:
                    continue
                seen.add((member_name, port))
                member_rows.append(
                    LtmPoolMember(
                        device=device,
                        pool_name=name,
                        name=member_name,
                        address=member.get("address", ""),
                        port=port,
                    )
                )

        created, updated = self.bulk_upsert(LtmPool, device, pool_rows, key_fields=("name",))

        # 整批一次清理 + 一次写入，不再按池逐条发语句
        if touched_pool_names:
            LtmPoolMember.objects.filter(device=device, pool_name__in=touched_pool_names).delete()
        if member_rows:
            LtmPoolMember.objects.bulk_create(member_rows, batch_size=500)
        return (created, updated)


class LBSnatSaver(BaseSaver):
    device_types = ["slb"]
    keys = ["snat_pools", "snat"]
    model_paths = ["assets.models.LtmSNAT"]

    def _save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import LtmSNAT

        snats = as_list(parsed_data.get("snat_pools") or parsed_data.get("snat"))
        if not snats:
            return (0, 0)

        created, updated = 0, 0
        for snat in snats:
            name = self._leaf(snat.get("name"))
            if not name:
                continue
            _, is_created = LtmSNAT.objects.update_or_create(
                device=device,
                name=name,
                defaults={"address": self._leaf(snat.get("address"))},
            )
            created += 1 if is_created else 0
            updated += 0 if is_created else 1
        return (created, updated)


class GTMWideipSaver(BaseSaver):
    device_types = ["gslb"]
    keys = ["wideips"]
    model_paths = ["assets.models.GtmWideip"]

    def _save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import GtmWideip

        wideips = as_list(parsed_data.get("wideips"))
        if not wideips:
            return (0, 0)

        created, updated = 0, 0
        for w in wideips:
            name = self._leaf(w.get("wideip_name") or w.get("name"))
            if not name:
                continue
            pools_raw = w.get("pools", [])
            if isinstance(pools_raw, list):
                pools = [
                    self._leaf(p.get("pool_name") or p.get("name")) if isinstance(p, dict) else self._leaf(p)
                    for p in pools_raw
                ]
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
    model_paths = ["assets.models.GtmDatacenter"]

    def _save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import GtmDatacenter
        from assets.serializers.views import GtmDatacenterSerializer

        created, updated = 0, 0
        for dc in as_list(parsed_data.get("datacenters")):
            name = self._leaf(dc.get("name"))
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
    model_paths = ["assets.models.GtmServer", "assets.models.GtmVServer"]

    def _save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import GtmServer, GtmVServer
        from assets.serializers.views import GtmServerSerializer, GtmVServerSerializer

        servers = as_list(parsed_data.get("servers"))
        if not servers:
            return (0, 0)

        server_rows = []
        pending_vservers: list[tuple[str, dict]] = []
        for srv in servers:
            name = self._leaf(srv.get("server_name"))
            if not name:
                continue
            server_rows.append(
                {
                    "name": name,
                    "datacenter": self._leaf(srv.get("datacenter")),
                    "monitor": self._leaf(srv.get("server_monitor")),
                    "server_type": srv.get("server_type") or "",
                }
            )
            # virtual-servers 是 servers 的子 group：一个 server 下挂多个 vserver
            for vs in as_list(srv.get("virtual_servers")):
                vs_name = self._leaf(vs.get("vs_name"))
                if vs_name:
                    pending_vservers.append((name, vs))

        created, updated = self.bulk_upsert(
            GtmServer, device, server_rows, key_fields=("name",), serializer_cls=GtmServerSerializer
        )

        # 父记录刚批量写完，一次取回 pk；原先每个 server 都要再 filter().first() 查一次
        server_ids = dict(GtmServer.objects.filter(device=device).values_list("name", "pk"))
        vs_rows = []
        for server_name, vs in pending_vservers:
            server_pk = server_ids.get(server_name)
            if server_pk is None:
                continue
            vs_rows.append(
                {
                    # server 给序列化器，server_id 只用于批量 upsert 的键（免掉一次 FK 查询）
                    "server": server_pk,
                    "server_id": server_pk,
                    "name": self._leaf(vs.get("vs_name")),
                    "ip_address": vs.get("vs_address") or None,
                    "port": str(vs.get("vs_port") or ""),
                    "monitor": self._leaf(vs.get("vs_monitor")),
                }
            )

        sub_created, sub_updated = self.bulk_upsert(
            GtmVServer,
            device,
            vs_rows,
            key_fields=("server_id", "name"),
            serializer_cls=GtmVServerSerializer,
        )
        return (created + sub_created, updated + sub_updated)


class GtmPoolSaver(BaseSaver):
    """GTM 池保存器，成员落 JSON 字段。"""

    device_types = ["gslb"]
    keys = ["pools"]
    model_paths = ["assets.models.GtmPool"]

    def _save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import GtmPool
        from assets.serializers.views import GtmPoolSerializer

        created, updated = 0, 0
        for pool in as_list(parsed_data.get("pools")):
            name = self._leaf(pool.get("pool_name"))
            if not name:
                continue
            monitor = self._leaf(pool.get("pool_monitor"))
            payload = {
                "name": name,
                "lb_mode": pool.get("preferred") or "round-robin",
                "alternate_mode": pool.get("alternate-mode") or "round-robin",
                "fallback_mode": pool.get("fallback-mode") or "return-to-dns",
                "ttl": self._safe_int(pool.get("ttl")) or 30,
                "monitor": [monitor] if monitor else [],
                "members": self._normalize_members(pool),
                "is_active": status_enabled(pool, "pool_status"),
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
            server = self._leaf(member.get("server_name"))
            if not server:
                continue
            members.append(
                {
                    "server": server,
                    "vserver": self._leaf(member.get("vs_name")),
                    # 双轨：新模板 enabled 0/1；手工 payload 给 status / 旧模板给 member_status
                    "status": "enabled" if status_enabled(member, "member_status", "status") else "disabled",
                    "order": self._safe_int(member.get("member_order")) or 0,
                    "ratio": self._safe_int(member.get("member_ratio")) or 1,
                    "monitor": self._leaf(member.get("member_monitor")),
                }
            )
        return members
