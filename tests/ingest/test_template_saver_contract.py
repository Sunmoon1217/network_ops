"""模板产出 ↔ Saver 的**结构**契约（端到端）。

键级对账由 ``test_parser_contract`` 守，但它看不见**元素结构**：hillstone 的动态组名
``services.{{ service_name }}`` / ``interfaces.{{ interface }}`` 把变量抬成字典键后，
``ServiceSaver`` / ``InterfaceSaver`` 按普通组的平铺结构读全部静默 ``continue``、
一行都存不进，而键级测试两边都有 ``services`` 这个键、照样是绿的（2026-09 实测盲区）。

这里用**真实模板**解析样例配置、喂**真实 Saver**，断言确实入库。
"""

import pytest

from assets.models import AddressBook, Device, Interface, Policy, Service
from ingest.parsers.factory import ParserFactory
from ingest.savers.firewall import AddressBookSaver, PolicySaver, ServiceSaver
from ingest.savers.interface import InterfaceSaver

HILLSTONE_CONFIG = """interface ge0/1
exit
interface ge0/2
exit
service "HTTP"
  tcp dst 80
exit
service "DNS"
  udp dst 53
  udp src 53
exit
address "web-servers"
  ip 203.0.113.0/24
exit
rule id 9
  action permit
  src-ip 10.0.0.0/24
  dst-addr "web-servers"
  service "HTTP"
  name "allow-web"
exit
"""


def _parsed(cfg: str = HILLSTONE_CONFIG) -> dict:
    return ParserFactory.get_parser_by_keys("Hillstone", "firewall").parse(cfg)


@pytest.mark.django_db
def test_services_from_dynamic_group_are_saved():
    """动态组名 services.{{ service_name }} 的 {服务名: 内容} 结构要展开成记录"""
    device = Device.objects.create(hostname="_t_tpl_svc", device_type="firewall")

    created, _ = ServiceSaver().save(device, _parsed())
    assert created == 2  # HTTP + DNS——旧结构下这里是 0（全部静默 continue）

    http = Service.objects.get(device=device, name="HTTP")
    assert (http.protocol, http.port) == ("tcp", "80")

    dns = Service.objects.get(device=device, name="DNS")
    assert dns.protocol == "udp"
    assert dns.port == "53"  # dst 行
    assert dns.port2 == ""  # src 行不进 port2（那是"范围第二端"的语义）
    assert "src: 53" in dns.description


@pytest.mark.django_db
def test_interfaces_from_dynamic_group_are_saved():
    """动态组名 interfaces.{{ interface }} 的 {接口名: 内容} 结构要展开成记录"""
    device = Device.objects.create(hostname="_t_tpl_if", device_type="firewall")

    created, _ = InterfaceSaver().save(device, _parsed())
    assert created == 2  # ge0/1 + ge0/2——旧结构下这里是 0

    assert Interface.objects.filter(device=device).count() == 2


@pytest.mark.django_db
def test_addresses_policies_still_land_with_dynamic_dict():
    """addresses 一直是动态 dict（AddressBookSaver 早已兼容），与 service/interface 同批
    走完，确认整条 hillstone 解析链四类对象全部落库、策略引用到真实的 Service。"""
    device = Device.objects.create(hostname="_t_tpl_all", device_type="firewall")
    parsed = _parsed()

    ServiceSaver().save(device, parsed)
    InterfaceSaver().save(device, parsed)
    AddressBookSaver().save(device, parsed)
    PolicySaver().save(device, parsed)

    assert AddressBook.objects.filter(device=device, name="web-servers").exists()
    policy = Policy.objects.get(device=device, policy_id="9")
    # 策略引用的 HTTP 是 ServiceSaver 落下的真实记录（protocol=tcp，不是 any 占位）
    services = {s.name: s for s in policy.services.all()}
    assert services["HTTP"].protocol == "tcp"


@pytest.mark.django_db
def test_flat_manual_payload_still_accepted():
    """平铺单条形态（手工喂入 / 普通组）不许被动态展开逻辑误伤"""
    device = Device.objects.create(hostname="_t_tpl_flat", device_type="firewall")

    assert ServiceSaver().save(device, {"services": {"name": "MANUAL", "protocol": "tcp"}}) == (1, 0)
    assert Service.objects.get(device=device, name="MANUAL").protocol == "tcp"

    assert InterfaceSaver().save(device, {"interfaces": {"interface": "eth9", "mode": "access"}}) == (1, 0)
    assert Interface.objects.get(device=device, interface="eth9").mode == "access"
