"""防火墙数据保存器"""

import ipaddress
from logging import getLogger
from typing import Any

from .base import BaseSaver, as_list, status_enabled

logger = getLogger(__name__)

# 各厂商表达"放行/拒绝"的用词不同，统一到 Policy.action 的 choices（allow / deny）
_ACTION_ALIASES = {
    "permit": "allow",
    "allow": "allow",
    "accept": "allow",
    "pass": "allow",
    "deny": "deny",
    "drop": "deny",
    "reject": "deny",
    "discard": "deny",
}


class AddressBookSaver(BaseSaver):
    """地址簿保存器。

    hillstone 用动态组名 ``addresses.{{ address_name }}``，**地址簿名在字典的键上、
    不在记录体里**：父记录按字典键建（``address_type="addressbook"``），各地址条目作为
    ``parent`` 指向它。产出形态与尚未落库的内容见 docs/ingest.md
    """

    device_types = ["firewall"]
    keys = ["address_books", "addresses"]
    model_paths = ["assets.models.AddressBook"]

    def _save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import AddressBook
        from assets.serializers.views import AddressBookSerializer

        # addresses 别名已由 ingest.mapping 在 save 入口归一为 address_books
        raw = parsed_data.get("address_books")
        if not raw:
            return (0, 0)

        entries = [(name, body) for name, body in self._entries(raw) if name]

        created, updated = self.bulk_upsert(
            AddressBook,
            device,
            [{"name": name, "address_type": "addressbook"} for name, _ in entries],
            key_fields=("name", "address_type"),
            serializer_cls=AddressBookSerializer,
        )

        # 父记录刚批量写完，一次把 pk 取回来；原先每本书都要再 filter().first() 查一次
        parent_ids = dict(
            AddressBook.objects.filter(device=device, address_type="addressbook").values_list("name", "pk")
        )

        child_rows = []
        for name, body in entries:
            parent_pk = parent_ids.get(name)
            if parent_pk is None:
                continue
            for payload in self._child_payloads(body):
                # parent 给序列化器，parent_id 只用于批量 upsert 的键（免掉一次 FK 查询）
                child_rows.append({**payload, "parent": parent_pk, "parent_id": parent_pk})

        sub_created, sub_updated = self.bulk_upsert(
            AddressBook,
            device,
            child_rows,
            key_fields=("parent_id", "address_type", "ip_address", "ip_start"),
            serializer_cls=AddressBookSerializer,
        )
        return (created + sub_created, updated + sub_updated)

    def _entries(self, raw) -> list[tuple[str | None, dict[str, Any]]]:
        """把产出归一成 ``[(地址簿名, 记录体)]``。

        主要形态是 ``{名字: 内容}`` 的字典；同时兼容带 ``name`` 字段的列表。
        """
        if isinstance(raw, dict):
            return [(name, body if isinstance(body, dict) else {"ip": body}) for name, body in raw.items()]
        return [(item.get("name"), item) for item in as_list(raw) if isinstance(item, dict)]

    def _child_payloads(self, body: dict) -> list[dict]:
        payloads = []
        for value in self._values(body.get("ip")):
            payload = self._from_cidr_or_host(value)
            if payload:
                payloads.append(payload)
        for value in self._values(body.get("host")):
            address = self._safe_ip(value)
            if address:
                payloads.append({"address_type": "host", "ip_address": address})
        for value in self._values(body.get("range")):
            payload = self._from_range(value)
            if payload:
                payloads.append(payload)

        # address "其他地址簿" 的引用没有模型字段可放，记进 description
        refs = [str(v) for v in self._values(body.get("addresses"))]
        if refs:
            for payload in payloads:
                payload["description"] = "引用: " + ", ".join(refs)
        return payloads

    def _values(self, value) -> list:
        """TTP 的 joinmatches/split 产出 list，单值也可能直接给字符串。"""
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return as_list(value)

    def _from_cidr_or_host(self, value) -> dict | None:
        """带 ``/`` 的当子网，否则当主机"""
        text = str(value).strip()
        if "/" in text:
            try:
                network = ipaddress.ip_network(text, strict=False)
            except ValueError:
                return None
            return {
                "address_type": "subnet",
                "ip_address": str(network.network_address),
                "ip_netmask": network.prefixlen,
            }
        address = self._safe_ip(text)
        return {"address_type": "host", "ip_address": address} if address else None

    def _from_range(self, value) -> dict | None:
        parts = [str(v) for v in self._values(value)]
        if len(parts) < 2:
            return None
        start, end = self._safe_ip(parts[0]), self._safe_ip(parts[1])
        if not start or not end:
            return None
        return {"address_type": "range", "ip_start": start, "ip_end": end}


class NatRuleSaver(BaseSaver):
    """NAT 规则保存器。

    ``cisco_fw.ttp`` 的 nat group 产出 ASA 的「object network + nat static」结构，
    与 NatRule 不是一一对应；字段映射表、以及「配置里没写的维度在库里就为空」
    这条后果，见 docs/ingest.md
    """

    device_types = ["firewall"]
    keys = ["nat"]
    model_paths = ["assets.models.NatRule", "assets.models.AddressBook"]

    def _save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import NatRule
        from assets.serializers.views import NatRuleSerializer

        created, updated = 0, 0
        for index, rule in enumerate(as_list(parsed_data.get("nat"))):
            name = rule.get("network_name")
            if not name:
                continue

            payload = {
                "order": index,
                "name": name,
                "nat_type": "dnat",
                "enabled": True,
                "description": self._describe(rule),
            }
            source = self._ensure_address(device, rule.get("host_ip"), f"NAT-{name}-src")
            if source:
                payload["source_addresses"] = [source.pk]
            target = self._ensure_address(device, rule.get("public_ip"), f"NAT-{name}-dst")
            if target:
                payload["translated_destination"] = target.pk

            is_new = self.upsert(NatRuleSerializer, NatRule, device, {"order": index}, payload)
            created += 1 if is_new else 0
            updated += 0 if is_new else 1
        return (created, updated)

    def _ensure_address(self, device, value, name: str):
        """把 IP 落成 AddressBook，供 NAT 规则的 M2M / 外键关联。

        用 get_or_create 而不是覆盖：同名地址簿可能是人工维护的，不擅自改它的地址。
        """
        from assets.models import AddressBook

        address = self._safe_ip(value)
        if not address:
            return None
        book, _ = AddressBook.objects.get_or_create(
            device=device,
            name=name,
            address_type="host",
            defaults={"ip_address": address},
        )
        return book

    def _describe(self, rule: dict) -> str:
        inside = rule.get("inside_interface")
        outside = rule.get("outside_interface")
        if not inside and not outside:
            return ""
        return f"nat ({inside or '?'},{outside or '?'})"


class ServiceSaver(BaseSaver):
    device_types = ["firewall"]
    keys = ["services"]
    model_paths = ["assets.models.Service"]

    def _save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import Service

        entries = self._entries(parsed_data.get("services"))
        if not entries:
            return (0, 0)

        # 按服务名分组后做**自然键差量**：一个 service 块的多行是同一个名字下的多个端口
        # 定义，逐行落库不合并；在的行原样复用（pk 稳定 → 策略 M2M 不被级联打断），
        # 只建缺失、删多余。细节见 docs/ingest.md
        by_name: dict[str, list[dict]] = {}
        for svc in entries:
            name = str(svc.get("name") or "").strip()
            if name:
                by_name.setdefault(name, []).append(svc)

        created, updated = 0, 0
        for name, rows in by_name.items():
            want: dict[tuple[str, str, str], str] = {}
            for row in rows:
                key = (str(row.get("protocol") or "tcp"), str(row.get("port", "")), str(row.get("port2", "")))
                want[key] = str(row.get("description") or "")  # 同自然键后行覆盖前行

            existing = {
                (item.protocol, item.port, item.port2): item
                for item in Service.objects.filter(device=device, name=name)
            }
            to_create, to_update, to_delete = [], [], []
            for key, description in want.items():
                hit = existing.get(key)
                if hit is None:
                    to_create.append(
                        Service(
                            device=device,
                            name=name,
                            protocol=key[0],
                            port=key[1],
                            port2=key[2],
                            description=description,
                        )
                    )
                elif hit.description != description:
                    hit.description = description
                    to_update.append(hit)
            to_delete = [item for key, item in existing.items() if key not in want]

            if to_create:
                Service.objects.bulk_create(to_create, batch_size=500)
                created += len(to_create)
            if to_update:
                Service.objects.bulk_update(to_update, ["description"], batch_size=500)
                updated += len(to_update)
            if to_delete:
                Service.objects.filter(pk__in=[item.pk for item in to_delete]).delete()
        return (created, updated)

    def _entries(self, raw) -> list[dict]:
        """把产出归一成 ``[{name, protocol, port, ...}]``，兼容平铺 / 动态字典 / 带星列表三种形态。

        结构级差异按分层约定留在 Saver；三种形态的样例见 docs/ingest.md
        """
        if isinstance(raw, dict):
            return [raw] if "name" in raw else self._expand(raw)
        rows: list[dict] = []
        for item in as_list(raw):
            if not isinstance(item, dict):
                continue
            rows.extend(self._expand(item)) if "name" not in item else rows.append(item)
        return rows

    @classmethod
    def _expand(cls, body: dict) -> list[dict]:
        """``{服务名: 内容}`` → ``[{name: 服务名, **该行字段}, ...]``，每行一条。

        为什么逐行不合并、src 行为什么单独成行：见 docs/ingest.md
        """
        records = []
        for name, content in body.items():
            for row in content if isinstance(content, list) else [content]:
                if not isinstance(row, dict):
                    continue
                record = {"name": name, **row}
                if str(row.get("port_type") or "dst").lower() == "src" and row.get("port"):
                    record["description"] = f"src: {row['port']}"
                records.append(record)
        return records


class PolicySaver(BaseSaver):
    """防火墙策略保存器。

    三类原始键与字段差异已在 ``BaseSaver.save`` 入口由 ``ingest.mapping`` 归一；
    这里只处理**值语义**（permit→allow、enable/disable→bool）与 hillstone 的
    分列地址（``-ip`` / ``-addr`` / ``-range`` / ``-host``，约定见 docs/ingest.md）
    """

    device_types = ["firewall"]
    keys = ["policies", "acl", "rules"]
    model_paths = ["assets.models.Policy", "assets.models.AddressBook", "assets.models.Service"]

    def _save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import AddressBook, Policy, Service
        from assets.serializers.views import AddressBookSerializer, PolicySerializer

        # acl / rules 别名已由 ingest.mapping 在 save 入口归一为 policies
        policies = parsed_data.get("policies")
        if not policies:
            return (0, 0)

        # 第一遍只收集（规则本体 + 引用到的地址/服务），跨规则去重后统一批量落库：
        # 同一个地址簿会被大量规则引用，逐条各写一次要重复付 SELECT + 校验 + 写库。
        policy_rows: list[dict] = []
        address_specs: dict[tuple[str, str], dict] = {}
        service_specs: dict[str, None] = {}
        # (policy_id, 源地址键, 目的地址键, 服务名)
        references: list[tuple[str, list[tuple[str, str]], list[tuple[str, str]], list[str]]] = []

        for index, item in enumerate(as_list(policies)):
            # rule_id / acl_name / rule_name 已归一为 policy_id / name；
            # 取不到 policy_id 的规则没有稳定标识，无法 upsert，只能跳过
            policy_id = str(item.get("policy_id") or item.get("name") or "").strip()
            if not policy_id:
                continue

            policy_rows.append(
                {
                    "policy_id": policy_id,
                    "order": self._safe_int(item.get("order")) if item.get("order") is not None else index,
                    "name": str(item.get("name") or policy_id),
                    "action": self._normalize_action(item.get("action")),
                    "enabled": self._is_enabled(item),
                    "log": bool(item.get("log", False)),
                    "description": item.get("description", ""),
                }
            )
            services = self._collect_services(item)
            for name in services:
                service_specs[name] = None
            references.append(
                (
                    policy_id,
                    self._collect_addresses(address_specs, self._address_entries(item, "src")),
                    self._collect_addresses(address_specs, self._address_entries(item, "dst")),
                    services,
                )
            )

        if not policy_rows:
            return (0, 0)

        # 地址簿与服务先落库，拿到 pk 供 M2M 使用。计数只上报策略本身：
        # 地址簿/服务的账由各自的 Saver 报，这里再计一遍会让流水线汇总重复。
        self.bulk_upsert(
            AddressBook,
            device,
            list(address_specs.values()),
            key_fields=("name", "address_type"),
            serializer_cls=AddressBookSerializer,
        )

        # 服务只按名字定位，协议未知时先记 any（等 ServiceSaver 补全）；不能用
        # bulk_upsert——它用 payload 覆盖已有记录，会把 ServiceSaver 填好的 protocol 冲回 any。
        # 同名可有多行端口定义，所以收集 name→[pks]（挂全部端口行），不能是单 pk。
        ids_by_name: dict[str, list[int]] = {}
        for pk, name in Service.objects.filter(device=device).values_list("pk", "name"):
            ids_by_name.setdefault(name, []).append(pk)
        missing = [name for name in service_specs if name not in ids_by_name]
        if missing:
            Service.objects.bulk_create(
                [Service(device=device, name=name, protocol="any") for name in missing], batch_size=500
            )
            ids_by_name = {}
            for pk, name in Service.objects.filter(device=device).values_list("pk", "name"):
                ids_by_name.setdefault(name, []).append(pk)

        address_ids = {
            (name, address_type): pk
            for name, address_type, pk in AddressBook.objects.filter(device=device).values_list(
                "name", "address_type", "pk"
            )
        }

        # 策略本体批量落库；M2M 不放进 payload，关联表单独批量写
        created, updated = self.bulk_upsert(
            Policy, device, policy_rows, key_fields=("policy_id",), serializer_cls=PolicySerializer
        )

        policy_ids = dict(Policy.objects.filter(device=device).values_list("policy_id", "pk"))
        source_map: dict[int, set[int]] = {}
        destination_map: dict[int, set[int]] = {}
        service_map: dict[int, set[int]] = {}
        for policy_id, source_keys, destination_keys, names in references:
            policy_pk = policy_ids.get(policy_id)
            if policy_pk is None:
                continue
            source_map[policy_pk] = {address_ids[key] for key in source_keys if key in address_ids}
            destination_map[policy_pk] = {address_ids[key] for key in destination_keys if key in address_ids}
            service_map[policy_pk] = {pk for name in names for pk in ids_by_name.get(name, ())}

        self._replace_m2m(Policy, "source_addresses", source_map)
        self._replace_m2m(Policy, "destination_addresses", destination_map)
        self._replace_m2m(Policy, "services", service_map)

        # 策略落库后重建该设备的访问流：投递即返回，展开与入库走独立队列 + 单写者
        # consumer（见 docs/analysis.md）。broker 不可达只告警不抛——入库已成功，可手工补。
        from ingest.access_flow_trigger import request_rebuild

        request_rebuild(device.pk)
        return (created, updated)

    def _replace_m2m(self, model, field_name: str, mapping: dict[int, set[int]]) -> None:
        """成批重置一个 M2M 关联：一次删除 + 一次 bulk_create。

        逐条 ``instance.m2m.set(ids)`` 每个策略要发 3 条左右的语句；规则上百条时
        这一项就占了大头，所以直接写 through 表。
        """
        field = getattr(model, field_name)
        through = field.through
        foreign_keys = [f for f in through._meta.get_fields() if f.many_to_one]
        owner_fk = next(f for f in foreign_keys if f.related_model is model)
        target_fk = next(f for f in foreign_keys if f.related_model is not model)

        if not mapping:
            return
        # 用 attname（policy_id / addressbook_id）而不是字段名：字段名那个描述符
        # 只接受模型实例，传 pk 会报 "must be a Policy instance"
        through.objects.filter(**{f"{owner_fk.attname}__in": list(mapping)}).delete()
        rows = [
            through(**{owner_fk.attname: owner_id, target_fk.attname: target_id})
            for owner_id, target_ids in mapping.items()
            for target_id in target_ids
        ]
        if rows:
            through.objects.bulk_create(rows, batch_size=500)

    def _normalize_action(self, action) -> str:
        """厂商用 permit / deny 等词，模型 choices 只有 allow / deny"""
        return _ACTION_ALIASES.get(str(action or "").strip().lower(), "allow")

    def _is_enabled(self, item: dict) -> bool:
        """双轨：新模板统一 ``enabled`` 0/1；旧/手工形态 hillstone 给 rule_status（enable/disable）"""
        return status_enabled(item, "rule_status")

    def _address_entries(self, item: dict, side: str) -> list[dict]:
        """把分列地址与通用列表两种形态统一成 ``[{kind, value}]``

        地址簿引用在模板里写作 ``src-address`` / ``dst-address``（TTP 变量名即产出键），
        这里同时兼容 ``-addr`` 写法。
        """
        entries: list[dict[str, Any]] = []
        for key, kind in (
            (f"{side}-ip", "ip"),
            (f"{side}-address", "book"),
            (f"{side}-addr", "book"),
            (f"{side}-range", "range"),
            (f"{side}-host", "host"),
        ):
            entries.extend({"kind": kind, "value": value} for value in as_list(item.get(key)))

        generic_key = "source_addresses" if side == "src" else "destination_addresses"
        for value in as_list(item.get(generic_key)):
            if isinstance(value, dict):
                value = value.get("name", "")
            entries.append({"kind": "book", "value": value})
        return entries

    def _collect_addresses(self, specs: dict[tuple[str, str], dict], entries: list[dict]) -> list[tuple[str, str]]:
        """把地址条目收进 ``specs``（按 ``(名字, 类型)`` 去重），返回本条规则用到的键。

        只收集不落库：真正的写库由 ``save`` 统一批量完成。
        """
        keys: list[tuple[str, str]] = []
        for entry in entries:
            payload = self._address_payload(entry)
            if not payload:
                continue
            key = (payload["name"], payload["address_type"])
            specs[key] = payload
            keys.append(key)
        return keys

    def _address_payload(self, entry: dict) -> dict | None:
        kind = entry["kind"]
        value = str(entry["value"] or "").strip()
        if not value:
            return None

        if kind == "book":
            # 地址簿引用：只记引用关系，内容由 AddressBookSaver 负责填
            return {"name": value, "address_type": "addressbook"}
        if kind == "range":
            parts = value.split()
            if len(parts) < 2:
                return None
            start, end = self._safe_ip(parts[0]), self._safe_ip(parts[1])
            if not start or not end:
                return None
            return {"name": f"{start}-{end}", "address_type": "range", "ip_start": start, "ip_end": end}
        if kind == "host":
            address = self._safe_ip(value)
            return {"name": address, "address_type": "host", "ip_address": address} if address else None

        # kind == "ip"：带 / 当子网，否则当主机
        if "/" in value:
            try:
                network = ipaddress.ip_network(value, strict=False)
            except ValueError:
                return None
            return {
                "name": str(network),
                "address_type": "subnet",
                "ip_address": str(network.network_address),
                "ip_netmask": network.prefixlen,
            }
        address = self._safe_ip(value)
        return {"name": address, "address_type": "host", "ip_address": address} if address else None

    def _collect_services(self, item: dict) -> list[str]:
        """取本条规则引用的服务名（单条规则内去重）。

        跨规则的汇总由 ``save`` 负责——只收集不落库，写库统一批量做。
        """
        used: dict[str, None] = {}
        for value in as_list(item.get("service")):
            name = str(value or "").strip()
            if name:
                used[name] = None
        return list(used)
