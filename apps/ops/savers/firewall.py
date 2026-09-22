"""防火墙数据保存器"""

import ipaddress
from logging import getLogger
from typing import Any

from .base import BaseSaver, as_list

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

    hillstone 模板用动态组名 ``addresses.{{ address_name }}``，产出形如::

        {"addresses": {"office": {"ip": ["10.0.0.0/24"]},
                       "web": {"host": ["1.1.1.1"],
                               "range": [["3.3.3.1", "3.3.3.10"]]}}}

    即**地址簿名在字典的键上、不在记录体里**，所以父记录按字典键建
    （``address_type="addressbook"``），各地址条目作为 ``parent`` 指向它的子记录。

    尚未落库的内容：``address "其他地址簿"`` 这种地址簿引用，模型没有对应字段，
    只能记进 ``description``。
    """

    device_types = ["firewall"]
    keys = ["address_books", "addresses"]
    model_paths = ["assets.models.AddressBook"]

    def _save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import AddressBook
        from assets.serializers.views import AddressBookSerializer

        # addresses 别名已由 ops.mapping 在 save 入口归一为 address_books
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

    ``cisco_fw.ttp`` 的 nat group 产出的是 ASA 的 "object network + nat static" 结构::

        {"network_name": "web", "host_ip": "10.0.0.10",
         "inside_interface": "inside", "outside_interface": "outside",
         "public_ip": "203.0.113.10"}

    它与 NatRule 模型不是一一对应，映射约定如下：

    - ``name`` ← ``network_name``
    - ``order`` ← 产出列表序号（模型上是 ``unique(device, order)``，故用它做 upsert 键）
    - ``nat_type`` 固定 ``dnat``：``nat (inside,outside) static`` 是入向目的地址转换
    - ``source_addresses`` ← ``host_ip``，先落成 AddressBook 再关联
    - ``translated_destination`` ← ``public_ip``，同样先落成 AddressBook
    - ``description`` ← ``nat (inside,outside)`` 的接口对
    - ``services`` 留空：cisco 的 nat group 给不出任何服务信息

    意味着配置里没写的维度（目标地址、服务）在库里就是空的，这也是这三个
    M2M 改成 ``blank=True`` 的原因。
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

        services = as_list(parsed_data.get("services"))
        if not services:
            return (0, 0)

        created, updated = 0, 0
        for svc in services:
            name = svc.get("name")
            if not name:
                continue
            _, is_created = Service.objects.update_or_create(
                device=device,
                name=name,
                defaults={
                    "protocol": svc.get("protocol", "tcp"),
                    "port": str(svc.get("port", "")),
                    "port2": str(svc.get("port2", "")),
                    "description": svc.get("description", ""),
                },
            )
            created += 1 if is_created else 0
            updated += 0 if is_created else 1
        return (created, updated)


class PolicySaver(BaseSaver):
    """防火墙策略保存器。

    三种原始产出键（``policies`` / ``acl``（cisco）/ ``rules``（hillstone））与
    字段差异（``rule_id`` / ``acl_name`` → ``policy_id``、``rule_name`` → ``name``）
    都已在 ``BaseSaver.save`` 入口由 ``ops.mapping`` 归一，这里只处理**值语义**
    与 hillstone 的结构级特征：

    - ``rules``（hillstone）：扁平的分列地址——``src-ip`` / ``src-addr`` / ``src-range`` /
      ``dst-ip`` / ``dst-addr`` / ``dst-range`` / ``dst-host`` / ``service`` / ``rule_status``

    hillstone 的地址按来源分列，转换约定：

    - ``-ip``：带 ``/`` 是子网（顺带拆出 ``ip_netmask``），不带是主机
    - ``-addr``：**地址簿引用**，按名字取用；地址簿不存在时先建占位记录，内容留给
      AddressBookSaver 去填
    - ``-range``：``"起始 结束"`` 形式，拆成 ``ip_start`` / ``ip_end``
    - ``-host``：主机地址
    """

    device_types = ["firewall"]
    keys = ["policies", "acl", "rules"]
    model_paths = ["assets.models.Policy", "assets.models.AddressBook", "assets.models.Service"]

    def _save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import AddressBook, Policy, Service
        from assets.serializers.views import AddressBookSerializer, PolicySerializer

        # acl / rules 别名已由 ops.mapping 在 save 入口归一为 policies
        policies = parsed_data.get("policies")
        if not policies:
            return (0, 0)

        # 第一遍只做收集：规则本体，以及它引用到的地址 / 服务。
        # 同一个地址簿会被大量规则引用，逐条规则各解析一次的话 SELECT + 校验 + 写库
        # 都要重复付，所以先跨规则去重，再统一批量落库。
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

        # ---- 地址簿与服务先落库，拿到 pk 供 M2M 使用 ----
        # 计数只上报策略本身：地址簿 / 服务的账由 AddressBookSaver、ServiceSaver 报，
        # 这里也计一遍会让流水线汇总重复（与改动前的语义保持一致）
        self.bulk_upsert(
            AddressBook,
            device,
            list(address_specs.values()),
            key_fields=("name", "address_type"),
            serializer_cls=AddressBookSerializer,
        )

        # 服务只按名字定位，协议未知时先记 any（等 ServiceSaver 补全）。
        # 这里不能用 bulk_upsert：它会用 payload 覆盖已有记录，把 ServiceSaver
        # 填好的 protocol 冲成 any，与原先 get_or_create 的语义不符。
        service_ids = dict(Service.objects.filter(device=device).values_list("name", "pk"))
        missing = [name for name in service_specs if name not in service_ids]
        if missing:
            Service.objects.bulk_create(
                [Service(device=device, name=name, protocol="any") for name in missing], batch_size=500
            )
            service_ids = dict(Service.objects.filter(device=device).values_list("name", "pk"))

        address_ids = {
            (name, address_type): pk
            for name, address_type, pk in AddressBook.objects.filter(device=device).values_list(
                "name", "address_type", "pk"
            )
        }

        # ---- 策略本体批量落库（M2M 不放进 payload，关联表单独批量写）----
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
            service_map[policy_pk] = {service_ids[name] for name in names if name in service_ids}

        self._replace_m2m(Policy, "source_addresses", source_map)
        self._replace_m2m(Policy, "destination_addresses", destination_map)
        self._replace_m2m(Policy, "services", service_map)

        # 策略落库后重建该设备的访问流（AccessFlow）：投递即返回，真正的展开与入库
        # 走独立的 access_flow 队列 + 单写者 consumer（见 ops/access_stream.py）。
        # broker 不可达只告警不抛出——解析入库已经成功，重建可手工补。
        # 延迟 import 并走 access_stream.request_rebuild：测试靠
        # ACCESS_FLOW_DISPATCH=0（conftest 统一设置）在这里拦掉真实投递。
        from ops.access_stream import request_rebuild

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
        """hillstone 用 rule_status（enable/disable），其它形态用 enabled"""
        status = item.get("rule_status")
        if status is not None:
            return str(status).strip().lower() not in {"disable", "disabled"}
        return bool(item.get("enabled", True))

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
