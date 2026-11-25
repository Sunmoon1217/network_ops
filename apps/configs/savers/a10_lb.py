"""A10 SLB 数据保存器：与 F5 共用一个 ``Ltm*`` 模型，配置语义的差异见 handbook/ingest.md「A10 SLB Saver」。"""

from logging import getLogger

from .base import BaseSaver, as_list, status_enabled

logger = getLogger(__name__)


class A10ServiceGroupSaver(BaseSaver):
    """A10 service-group 保存器：service-group → LtmPool + LtmPoolMember。"""

    device_types = ["slb"]
    keys = ["service_groups"]
    model_paths = ["configs.models.LtmPool", "configs.models.LtmPoolMember"]

    def _save(self, device, parsed_data: dict) -> tuple[int, int]:
        from configs.models import LtmPool, LtmPoolMember

        groups = as_list(parsed_data.get("service_groups"))
        if not groups:
            return (0, 0)

        pool_rows = []
        member_rows = []
        touched_pool_names: list[str] = []

        for group in groups:
            if not isinstance(group, dict):
                continue
            name = self._leaf(group.get("name"))
            if not name:
                continue
            touched_pool_names.append(name)

            # A10 模板 monitor 在无 health-check 行时默认产出 "None"（字符串）
            monitor = self._leaf(group.get("monitor"))
            monitors = [monitor] if monitor and monitor != "None" else []

            pool_rows.append(
                {
                    "name": name,
                    "mode": group.get("method", ""),
                    "monitors": monitors,
                }
            )

            seen: set[tuple[str, str]] = set()
            for member in as_list(group.get("members")):
                if not isinstance(member, dict):
                    continue
                address = self._leaf(member.get("address"))
                if not address:
                    continue
                port = str(member.get("port") or "")
                if (address, port) in seen:
                    continue
                seen.add((address, port))
                member_rows.append(
                    LtmPoolMember(
                        device=device,
                        pool_name=name,
                        name=address,
                        address=address,
                        port=port,
                    )
                )

        created, updated = self.bulk_upsert(LtmPool, device, pool_rows, key_fields=("name",))

        # 成员没有自然键，只能「先清后建」；范围按「设备 + 池名」圈定（与 F5 LBPoolSaver 一致）
        if touched_pool_names:
            LtmPoolMember.objects.filter(device=device, pool_name__in=touched_pool_names).delete()
        if member_rows:
            LtmPoolMember.objects.bulk_create(member_rows, batch_size=500)
        return (created, updated)


class A10VirtualServerSaver(BaseSaver):
    """A10 virtual-server 保存器：virtual-server → LtmVirtualServer + LtmProfile + LtmPersist。"""

    device_types = ["slb"]
    keys = ["virtual_server"]
    model_paths = [
        "configs.models.LtmVirtualServer",
        "configs.models.LtmProfile",
        "configs.models.LtmPersist",
    ]

    def _save(self, device, parsed_data: dict) -> tuple[int, int]:
        from configs.models import LtmPersist, LtmProfile, LtmVirtualServer
        from configs.serializers.config import LtmPersistSerializer, LtmProfileSerializer

        servers = as_list(parsed_data.get("virtual_server"))
        if not servers:
            return (0, 0)

        vs_rows = []
        # 设备级清单：同名 profile / persist 只留一条，后来者覆盖（与 F5 语义一致）
        profiles: dict[str, dict] = {}
        persists: dict[str, dict] = {}

        for server in servers:
            if not isinstance(server, dict):
                continue
            vs_name = self._leaf(server.get("name"))
            if not vs_name:
                continue
            vs_address = server.get("address") or ""

            for svc in as_list(server.get("virtual_services")):
                if not isinstance(svc, dict):
                    continue
                port = str(svc.get("port") or "")
                if not port:
                    continue
                name = f"{vs_name}:{port}"

                http_tmpl = self._leaf(svc.get("http_tmpl"))
                ssl_name = self._leaf(svc.get("ssl_name"))
                profile_names = [p for p in (http_tmpl, ssl_name) if p]

                persist_type = self._leaf(svc.get("persist_type"))
                persist_name = self._leaf(svc.get("persist_name"))

                vs_rows.append(
                    {
                        "name": name,
                        "vs_address": vs_address,
                        "vs_port": port,
                        "protocol": svc.get("protocol", ""),
                        "status": "enabled" if status_enabled(svc) else "disabled",
                        "pool": self._leaf(svc.get("service_group")),
                        "snat_type": svc.get("snat_type", ""),
                        "snat_pool": self._leaf(svc.get("snat_pool")),
                        "persist": persist_name or None,
                        "profiles": profile_names,
                    }
                )

                if http_tmpl:
                    profiles[http_tmpl] = {"name": http_tmpl, "type": "http", "raw": {"name": http_tmpl, "virtual_server": name}}
                if ssl_name:
                    profiles[ssl_name] = {"name": ssl_name, "type": "client-ssl", "raw": {"name": ssl_name, "virtual_server": name}}
                if persist_name:
                    persists[persist_name] = {
                        "name": persist_name,
                        "type": persist_type or persist_name,
                        "raw": {"name": persist_name, "virtual_server": name},
                    }

        created, updated = self.bulk_upsert(LtmVirtualServer, device, vs_rows, key_fields=("name",))
        for model, rows, serializer_cls in (
            (LtmProfile, list(profiles.values()), LtmProfileSerializer),
            (LtmPersist, list(persists.values()), LtmPersistSerializer),
        ):
            sub_created, sub_updated = self.bulk_upsert(model, device, rows, key_fields=("name",), serializer_cls=serializer_cls)
            created += sub_created
            updated += sub_updated
        return (created, updated)
