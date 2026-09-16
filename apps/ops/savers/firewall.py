"""防火墙数据保存器"""

import ipaddress
from logging import getLogger

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

    def save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import AddressBook
        from assets.serializers.views import AddressBookSerializer

        raw = parsed_data.get("address_books") or parsed_data.get("addresses")
        if not raw:
            return (0, 0)

        created, updated = 0, 0
        for name, body in self._entries(raw):
            if not name:
                continue

            is_new = self.upsert(
                AddressBookSerializer,
                AddressBook,
                device,
                {"name": name, "address_type": "addressbook"},
                {"name": name, "address_type": "addressbook"},
            )
            created += 1 if is_new else 0
            updated += 0 if is_new else 1

            parent = AddressBook.objects.filter(device=device, name=name, address_type="addressbook").first()
            for payload in self._child_payloads(body):
                is_new_child = self.upsert(
                    AddressBookSerializer,
                    AddressBook,
                    device,
                    {
                        "parent": parent,
                        "address_type": payload["address_type"],
                        "ip_address": payload.get("ip_address"),
                        "ip_start": payload.get("ip_start"),
                    },
                    {**payload, "parent": parent.pk},
                )
                created += 1 if is_new_child else 0
                updated += 0 if is_new_child else 1
        return (created, updated)

    def _entries(self, raw) -> list[tuple[str, dict]]:
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

    def save(self, device, parsed_data: dict) -> tuple[int, int]:
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

    def save(self, device, parsed_data: dict) -> tuple[int, int]:
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

    三种产出形态共用：

    - ``policies`` / ``acl``（cisco）：带 ``policy_id`` / ``order`` / ``action`` / ``enabled``
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

    def save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import Policy
        from assets.serializers.views import PolicySerializer

        policies = parsed_data.get("policies") or parsed_data.get("acl") or parsed_data.get("rules")
        if not policies:
            return (0, 0)

        created, updated = 0, 0
        for index, item in enumerate(as_list(policies)):
            policy_id = str(item.get("policy_id") or item.get("rule_id") or item.get("name") or "").strip()
            if not policy_id:
                continue

            payload = {
                "policy_id": policy_id,
                "order": self._safe_int(item.get("order")) if item.get("order") is not None else index,
                "name": str(item.get("name") or item.get("rule_name") or policy_id),
                "action": self._normalize_action(item.get("action")),
                "enabled": self._is_enabled(item),
                "log": bool(item.get("log", False)),
                "description": item.get("description", ""),
            }
            source_ids = self._resolve_addresses(device, self._address_entries(item, "src"))
            if source_ids:
                payload["source_addresses"] = source_ids
            destination_ids = self._resolve_addresses(device, self._address_entries(item, "dst"))
            if destination_ids:
                payload["destination_addresses"] = destination_ids
            service_ids = self._resolve_services(device, item)
            if service_ids:
                payload["services"] = service_ids

            is_new = self.upsert(PolicySerializer, Policy, device, {"policy_id": policy_id}, payload)
            created += 1 if is_new else 0
            updated += 0 if is_new else 1
        return (created, updated)

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
        entries = []
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

    def _resolve_addresses(self, device, entries: list[dict]) -> list[int]:
        from assets.models import AddressBook
        from assets.serializers.views import AddressBookSerializer

        ids = []
        for entry in entries:
            payload = self._address_payload(entry)
            if not payload:
                continue
            book = AddressBook.objects.filter(
                device=device, name=payload["name"], address_type=payload["address_type"]
            ).first()
            serializer = AddressBookSerializer(book, data={**payload, "device": device.pk}, partial=True)
            serializer.is_valid(raise_exception=True)
            ids.append(serializer.save().pk)
        return ids

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

    def _resolve_services(self, device, item: dict) -> list[int]:
        """服务名落成 Service 记录；协议未知时记 any，等 ServiceSaver 补全"""
        from assets.models import Service

        ids = []
        for value in as_list(item.get("service")):
            name = str(value or "").strip()
            if not name:
                continue
            service, _ = Service.objects.get_or_create(device=device, name=name, defaults={"protocol": "any"})
            ids.append(service.pk)
        return ids
