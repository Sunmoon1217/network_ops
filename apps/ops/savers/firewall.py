"""防火墙数据保存器"""

import ipaddress
from logging import getLogger

from .base import BaseSaver, as_list

logger = getLogger(__name__)


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

        services = parsed_data.get("services", [])
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
    device_types = ["firewall"]
    keys = ["policies", "acl"]

    def save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import Policy

        policies = parsed_data.get("policies", parsed_data.get("acl", []))
        if not policies:
            return (0, 0)

        created, updated = 0, 0
        for p in policies:
            policy_id = p.get("policy_id", p.get("name", ""))
            if not policy_id:
                continue
            _, is_created = Policy.objects.update_or_create(
                device=device,
                policy_id=policy_id,
                defaults={
                    "order": p.get("order", 0),
                    "name": p.get("name", policy_id),
                    "action": p.get("action", "allow"),
                    "enabled": p.get("enabled", True),
                    "log": p.get("log", False),
                    "description": p.get("description", ""),
                },
            )
            created += 1 if is_created else 0
            updated += 0 if is_created else 1
        return (created, updated)
