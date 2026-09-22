"""AddressBook Saver 测试。

用 Hillstone 解析器的**真实产出**驱动（模板用动态组名 ``addresses.{{ name }}``，
地址簿名在字典键上），避免测试里手搓结构与模板脱节。
"""

import pytest

from assets.models import AddressBook, Device
from ingest.parsers.factory import ParserFactory
from ingest.savers.firewall import AddressBookSaver

HILLSTONE_ADDRESSES = """address "office"
  ip 10.0.0.0/24
exit
address "web-servers"
  host 1.1.1.1
  host 2.2.2.2
  range 3.3.3.1 3.3.3.10
exit
"""


def _parsed() -> dict:
    return ParserFactory.get_parser_by_keys("Hillstone", "firewall").parse(HILLSTONE_ADDRESSES)


@pytest.mark.django_db
def test_address_book_parent_and_children():
    """地址簿建父记录，各地址条目作为子记录挂在 parent 下"""
    device = Device.objects.create(hostname="_t_ab_fw", device_type="firewall")

    created, updated = AddressBookSaver().save(device, _parsed())
    # 2 个父地址簿 + office 的 1 个子网 + web-servers 的 2 主机 1 范围
    assert (created, updated) == (6, 0)

    office = AddressBook.objects.get(device=device, name="office", address_type="addressbook")
    assert office.parent is None
    subnet = AddressBook.objects.get(device=device, parent=office)
    assert subnet.address_type == "subnet"
    assert subnet.ip_address == "10.0.0.0"
    assert subnet.ip_netmask == 24


@pytest.mark.django_db
def test_host_and_range_entries():
    device = Device.objects.create(hostname="_t_ab_host", device_type="firewall")
    AddressBookSaver().save(device, _parsed())

    web = AddressBook.objects.get(device=device, name="web-servers", address_type="addressbook")
    children = AddressBook.objects.filter(device=device, parent=web)
    assert children.count() == 3

    hosts = sorted(str(ip) for ip in children.filter(address_type="host").values_list("ip_address", flat=True))
    assert hosts == ["1.1.1.1", "2.2.2.2"]

    address_range = children.get(address_type="range")
    assert (str(address_range.ip_start), str(address_range.ip_end)) == ("3.3.3.1", "3.3.3.10")


@pytest.mark.django_db
def test_address_book_is_idempotent():
    """同一份解析结果重复入库不得产生重复记录"""
    device = Device.objects.create(hostname="_t_ab_idem", device_type="firewall")
    saver = AddressBookSaver()
    parsed = _parsed()

    assert saver.save(device, parsed)[0] == 6
    assert saver.save(device, parsed) == (0, 6)
    assert AddressBook.objects.filter(device=device).count() == 6


@pytest.mark.django_db
def test_address_reference_goes_to_description():
    """address "其他地址簿" 的引用模型没有对应字段，落进 description"""
    device = Device.objects.create(hostname="_t_ab_ref", device_type="firewall")
    parsed = {"addresses": {"combined": {"host": ["1.1.1.1"], "addresses": ["office", "web"]}}}

    AddressBookSaver().save(device, parsed)

    child = AddressBook.objects.get(device=device, address_type="host")
    assert "引用: office, web" in child.description


@pytest.mark.django_db
def test_invalid_address_is_skipped():
    """非法地址不能写进 GenericIPAddressField，直接跳过"""
    device = Device.objects.create(hostname="_t_ab_bad", device_type="firewall")
    parsed = {"addresses": {"mixed": {"host": ["1.1.1.1", "not-an-ip"]}}}

    assert AddressBookSaver().save(device, parsed) == (2, 0)  # 1 个父 + 1 个有效子
    assert AddressBook.objects.filter(device=device, address_type="host").count() == 1


@pytest.mark.django_db
def test_cidr_without_prefix_is_treated_as_host():
    """不带 / 的 ip 按主机处理，带 / 的按子网处理"""
    device = Device.objects.create(hostname="_t_ab_cidr", device_type="firewall")
    parsed = {"addresses": {"mixed": {"ip": ["10.0.0.0/24", "10.0.0.5"]}}}

    AddressBookSaver().save(device, parsed)

    entries = AddressBook.objects.filter(device=device, address_type__in=["subnet", "host"])
    types = dict(entries.values_list("address_type", "ip_address"))
    assert types == {"subnet": "10.0.0.0", "host": "10.0.0.5"}


@pytest.mark.django_db
def test_legacy_list_shape_with_name_field():
    """兼容带 name 字段的 address_books 列表形态"""
    device = Device.objects.create(hostname="_t_ab_legacy", device_type="firewall")
    parsed = {"address_books": [{"name": "legacy", "ip": ["192.168.0.0/24"]}]}

    assert AddressBookSaver().save(device, parsed) == (2, 0)

    parent = AddressBook.objects.get(device=device, name="legacy", address_type="addressbook")
    assert AddressBook.objects.get(device=device, parent=parent).ip_address == "192.168.0.0"


@pytest.mark.django_db
def test_empty_payload_is_noop():
    device = Device.objects.create(hostname="_t_ab_empty", device_type="firewall")
    assert AddressBookSaver().save(device, {}) == (0, 0)
    assert AddressBook.objects.filter(device=device).count() == 0
