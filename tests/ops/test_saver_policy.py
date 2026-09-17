"""PolicySaver 测试。

hillstone 的 ``rules`` 是扁平的分列地址（``src-ip`` / ``src-addr`` / ``src-range`` ...），
这里验证它被正确落成 Policy 及其三个 M2M。
"""

import pytest

from assets.models import AddressBook, Device, Policy, Service
from ops.parsers.factory import ParserFactory
from ops.savers.firewall import PolicySaver

HILLSTONE_RULE = """rule id 9
  action permit
  src-zone "trust"
  dst-zone "untrust"
  src-ip 10.0.0.0/24
  src-addr "office-group"
  src-range 10.1.1.1 10.1.1.9
  dst-ip 203.0.113.10
  dst-addr "web-servers"
  dst-range 203.0.113.20 203.0.113.29
  dst-host "10.0.0.99"
  service "HTTP"
  name "ranged-rule"
exit
"""


def _parsed(cfg: str = HILLSTONE_RULE) -> dict:
    return ParserFactory.get_parser_by_keys("Hillstone", "firewall").parse(cfg)


@pytest.mark.django_db
def test_rule_saved_with_scalar_fields():
    device = Device.objects.create(hostname="_t_pol_fw", device_type="firewall")

    assert PolicySaver().save(device, _parsed()) == (1, 0)

    policy = Policy.objects.get(device=device, policy_id="9")
    assert policy.name == "ranged-rule"
    assert policy.action == "allow"  # permit 归一为模型的 allow
    assert policy.enabled is True


@pytest.mark.django_db
def test_source_addresses_split_by_type():
    """分列地址按类型落成 AddressBook：子网 / 地址簿引用 / 范围"""
    device = Device.objects.create(hostname="_t_pol_src", device_type="firewall")
    PolicySaver().save(device, _parsed())

    policy = Policy.objects.get(device=device, policy_id="9")
    sources = {address.address_type: address for address in policy.source_addresses.all()}

    assert sources["subnet"].ip_address == "10.0.0.0"
    assert sources["subnet"].ip_netmask == 24
    assert sources["addressbook"].name == "office-group"
    assert str(sources["range"].ip_start) == "10.1.1.1"
    assert str(sources["range"].ip_end) == "10.1.1.9"


@pytest.mark.django_db
def test_destination_addresses_include_ip_and_host_as_hosts():
    """不带 / 的 dst-ip 与 dst-host 都落成 host 类型"""
    device = Device.objects.create(hostname="_t_pol_dst", device_type="firewall")
    PolicySaver().save(device, _parsed())

    policy = Policy.objects.get(device=device, policy_id="9")
    destinations = {address.address_type: address for address in policy.destination_addresses.all()}
    assert destinations["addressbook"].name == "web-servers"
    assert str(destinations["range"].ip_end) == "203.0.113.29"

    hosts = sorted(str(address.ip_address) for address in policy.destination_addresses.filter(address_type="host"))
    assert hosts == ["10.0.0.99", "203.0.113.10"]


@pytest.mark.django_db
def test_services_linked():
    device = Device.objects.create(hostname="_t_pol_svc", device_type="firewall")
    PolicySaver().save(device, _parsed())

    policy = Policy.objects.get(device=device, policy_id="9")
    assert [service.name for service in policy.services.all()] == ["HTTP"]
    # 协议未知时先记 any，等 ServiceSaver 补全
    assert Service.objects.get(device=device, name="HTTP").protocol == "any"


@pytest.mark.django_db
def test_disabled_rule_maps_to_enabled_false():
    """hillstone 用 rule_status 表达启用状态"""
    device = Device.objects.create(hostname="_t_pol_off", device_type="firewall")
    cfg = 'rule id 10\n  action deny\n  disable\n  name "off"\n  service "TELNET"\nexit\n'

    PolicySaver().save(device, _parsed(cfg))

    assert Policy.objects.get(device=device, policy_id="10").enabled is False


@pytest.mark.django_db
def test_existing_address_book_is_reused():
    """src-addr 引用已存在的地址簿时复用，不新建"""
    device = Device.objects.create(hostname="_t_pol_reuse", device_type="firewall")
    existing = AddressBook.objects.create(device=device, name="office-group", address_type="addressbook")

    PolicySaver().save(device, _parsed())

    assert AddressBook.objects.filter(device=device, name="office-group").count() == 1
    policy = Policy.objects.get(device=device, policy_id="9")
    assert existing.pk in policy.source_addresses.values_list("pk", flat=True)


@pytest.mark.django_db
def test_rule_is_idempotent():
    device = Device.objects.create(hostname="_t_pol_idem", device_type="firewall")
    saver = PolicySaver()
    parsed = _parsed()

    assert saver.save(device, parsed) == (1, 0)
    assert saver.save(device, parsed) == (0, 1)
    assert Policy.objects.filter(device=device).count() == 1


@pytest.mark.django_db
def test_cisco_acl_shape_still_works():
    """通用形态（policy_id / order / action）不受 hillstone 改造影响"""
    device = Device.objects.create(hostname="_t_pol_cisco", device_type="firewall")
    parsed = {
        "acl": [
            {
                "policy_id": "100",
                "order": 0,
                "name": "allow-web",
                "action": "allow",
                "enabled": True,
                "source_addresses": ["office-group"],
            }
        ]
    }

    assert PolicySaver().save(device, parsed) == (1, 0)

    policy = Policy.objects.get(device=device, policy_id="100")
    assert policy.action == "allow"
    assert [address.name for address in policy.source_addresses.all()] == ["office-group"]


# ---------- 批量化改造后的语义守卫 ----------


@pytest.mark.django_db
def test_existing_service_protocol_is_not_clobbered():
    """PolicySaver 只补占位服务，不能把 ServiceSaver 填好的 protocol 冲成 any。

    批量化时如果把服务也走 bulk_upsert，payload 里的 protocol="any" 会覆盖已有记录。
    """
    device = Device.objects.create(hostname="_t_pol_svc_keep", device_type="firewall")
    Service.objects.create(device=device, name="HTTP", protocol="tcp", port="80")

    PolicySaver().save(device, _parsed())

    service = Service.objects.get(device=device, name="HTTP")
    assert service.protocol == "tcp"
    assert service.port == "80"


@pytest.mark.django_db
def test_m2m_links_are_replaced_not_accumulated():
    """重新保存时旧关联要被替换：换一套源地址后不能还留着上一次的链接"""
    device = Device.objects.create(hostname="_t_pol_m2m", device_type="firewall")
    saver = PolicySaver()
    saver.save(device, _parsed())

    policy = Policy.objects.get(device=device, policy_id="9")
    before = set(policy.source_addresses.values_list("name", flat=True))
    assert before

    # 真实模板用 | to_list 产出列表，裸字符串会被 as_list 丢掉
    saver.save(
        device,
        {"rules": [{"rule_id": "9", "action": "permit", "src-ip": ["192.168.7.7"], "dst-ip": ["10.0.0.1"]}]},
    )

    policy.refresh_from_db()
    assert set(policy.source_addresses.values_list("name", flat=True)) == {"192.168.7.7"}


@pytest.mark.django_db
def test_shared_address_book_is_written_once_for_many_rules():
    """多条规则引用同一个地址簿时，最终只有一条地址簿记录"""
    device = Device.objects.create(hostname="_t_pol_shared", device_type="firewall")
    rules = [
        {"rule_id": str(i), "action": "permit", "src-addr": ["office-group"], "dst-host": [f"10.0.0.{i}"]}
        for i in range(1, 6)
    ]

    PolicySaver().save(device, {"rules": rules})

    assert AddressBook.objects.filter(device=device, name="office-group", address_type="addressbook").count() == 1
    for i in range(1, 6):
        policy = Policy.objects.get(device=device, policy_id=str(i))
        assert [book.name for book in policy.source_addresses.all()] == ["office-group"]
