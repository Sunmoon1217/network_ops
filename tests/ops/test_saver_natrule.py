"""NatRule Saver 测试。

用 Cisco 解析器的**真实产出**驱动：它的 nat group 产出 ASA 的
"object network + nat static" 结构，与 NatRule 模型不是一一对应，
且完全给不出 service —— 这正是三个 M2M 改成 blank=True 的原因。
"""

import pytest

from assets.models import AddressBook, Device, NatRule
from ops.parsers.factory import ParserFactory
from ops.savers.firewall import NatRuleSaver

CISCO_NAT = """object network web
 host 10.0.0.10
 nat (inside,outside) static 203.0.113.10
"""


def _parsed() -> dict:
    return ParserFactory.get_parser_by_keys("Cisco", "firewall").parse(CISCO_NAT)


@pytest.mark.django_db
def test_nat_rule_saved_without_services():
    """cisco 给不出 service，规则仍须入库（三个 M2M 允许为空的直接收益）"""
    device = Device.objects.create(hostname="_t_nat_fw", device_type="firewall")

    # 计数只统计 NAT 规则本身；自动补建的 AddressBook 是辅助记录，不计入
    assert NatRuleSaver().save(device, _parsed()) == (1, 0)

    rule = NatRule.objects.get(device=device)
    assert rule.name == "web"
    assert rule.nat_type == "dnat"
    assert rule.order == 0
    assert rule.services.count() == 0
    assert rule.description == "nat (inside,outside)"
    assert [str(address.ip_address) for address in rule.source_addresses.all()] == ["10.0.0.10"]
    assert str(rule.translated_destination.ip_address) == "203.0.113.10"


@pytest.mark.django_db
def test_nat_rule_is_idempotent():
    device = Device.objects.create(hostname="_t_nat_idem", device_type="firewall")
    saver = NatRuleSaver()
    parsed = _parsed()

    assert saver.save(device, parsed) == (1, 0)
    assert saver.save(device, parsed) == (0, 1)
    assert NatRule.objects.filter(device=device).count() == 1
    assert AddressBook.objects.filter(device=device).count() == 2


@pytest.mark.django_db
def test_multiple_rules_get_sequential_order():
    device = Device.objects.create(hostname="_t_nat_multi", device_type="firewall")
    parsed = {
        "nat": [
            {"network_name": "a", "host_ip": "10.0.0.1", "public_ip": "203.0.113.1"},
            {"network_name": "b", "host_ip": "10.0.0.2", "public_ip": "203.0.113.2"},
        ]
    }

    assert NatRuleSaver().save(device, parsed) == (2, 0)

    ordered = NatRule.objects.filter(device=device).order_by("order").values_list("name", flat=True)
    assert list(ordered) == ["a", "b"]


@pytest.mark.django_db
def test_rule_without_ips_still_saves():
    """只有 network_name 时也能建规则，关联维度留空"""
    device = Device.objects.create(hostname="_t_nat_bare", device_type="firewall")

    assert NatRuleSaver().save(device, {"nat": {"network_name": "bare"}}) == (1, 0)

    rule = NatRule.objects.get(device=device)
    assert rule.source_addresses.count() == 0
    assert rule.translated_destination is None


@pytest.mark.django_db
def test_invalid_ip_does_not_create_address_book():
    """非法 IP 不应写进 GenericIPAddressField，也不该留下垃圾地址簿"""
    device = Device.objects.create(hostname="_t_nat_bad", device_type="firewall")
    parsed = {"nat": {"network_name": "bad", "host_ip": "not-an-ip", "public_ip": "203.0.113.5"}}

    NatRuleSaver().save(device, parsed)

    assert AddressBook.objects.filter(device=device).count() == 1  # 只有合法的目的地址
    assert NatRule.objects.get(device=device).source_addresses.count() == 0


@pytest.mark.django_db
def test_existing_address_book_is_reused():
    """同名地址簿已存在时复用，不覆盖它已有的地址"""
    device = Device.objects.create(hostname="_t_nat_reuse", device_type="firewall")
    AddressBook.objects.create(device=device, name="NAT-web-src", address_type="host", ip_address="192.168.1.1")

    NatRuleSaver().save(device, _parsed())

    rule = NatRule.objects.get(device=device)
    assert [str(address.ip_address) for address in rule.source_addresses.all()] == ["192.168.1.1"]
