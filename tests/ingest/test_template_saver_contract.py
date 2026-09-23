"""模板产出 ↔ Saver 的**结构**契约（端到端）。

键级对账由 ``test_parser_contract`` 守，但它看不见**元素结构**：hillstone 的动态组名
``services.{{ service_name }}`` / ``interfaces.{{ interface }}`` 把变量抬成字典键后，
``ServiceSaver`` / ``InterfaceSaver`` 按普通组的平铺结构读全部静默 ``continue``、
一行都存不进，而键级测试两边都有 ``services`` 这个键、照样是绿的（2026-09 实测盲区）。

这里用**真实模板**解析样例配置、喂**真实 Saver**，断言确实入库。
"""

import pytest
from django.conf import settings

from assets.models import AddressBook, Device, Interface, Policy, Service
from ingest.parsers.factory import ParserFactory
from ingest.savers.firewall import AddressBookSaver, PolicySaver, ServiceSaver
from ingest.savers.interface import InterfaceSaver
from ingest.savers.registry import build_saver_payloads

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


# ---------------------------------------------------------------------------
# 全厂商样例端到端：有产出 + 有 Saver 的键必须入库 >0 行
# ---------------------------------------------------------------------------

SAMPLES = [
    ("cisco_fw", "Cisco", "firewall"),
    ("h3c_router", "H3C", "router"),
    ("h3c_switch", "H3C", "switch"),
    ("huawei_switch", "Huawei", "switch"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("fname,vendor,dtype", SAMPLES, ids=[s[0] for s in SAMPLES])
def test_sample_config_lands_in_db(fname, vendor, dtype):
    """样例配置走**生产分组路径**（build_saver_payloads）喂真实 Saver。

    判据只有一条：凡是「模板有产出、注册表有 Saver」的键，``created + updated``
    必须 > 0——hillstone service/interface 那类结构错位在键级测试下是绿的，
    在这里表现为静默 0 行并直接红灯。
    """
    from pathlib import Path

    cfg_path = Path(settings.BASE_DIR) / "data" / "configs" / f"{fname}.txt"
    if not cfg_path.exists():
        pytest.skip(f"缺少样例配置 {fname}.txt")
    cfg = cfg_path.read_text(encoding="utf-8")

    parsed = ParserFactory.get_parser_by_keys(vendor, dtype).parse(cfg)
    device = Device.objects.create(hostname=f"_t_sample_{fname}", device_type=dtype)

    payloads = build_saver_payloads(dtype, parsed)
    assert payloads, f"{fname}: 没有任何 Saver 被分组——键级对位已坏"

    for saver, payload in payloads:
        created, updated = saver.save(device, payload)
        assert created + updated > 0, (
            f"{fname}: {type(saver).__name__} 收到键 {sorted(payload)} 却 0 行入库"
            "——模板产出结构/字段与 Saver 不匹配（hillstone service 同类问题）"
        )


# ---------------------------------------------------------------------------
# 无样例文件厂商的内联配置端到端（F5 / A10 / Maipu / Ruijie）
# ---------------------------------------------------------------------------

_INLINE = [
    (
        "f5_slb",
        "F5",
        "slb",
        """ltm node /Common/node_a {
    address 10.0.0.1
}
ltm pool /Common/pool_x {
    load-balancing-mode round-robin
    monitor /Common/http
    members {
        /Common/node_a:80 {
            address 10.0.0.1
        }
    }
}
ltm virtual /Common/vs_x {
    destination /Common/10.0.0.100:80
    enabled
    ip-protocol tcp
    mask 255.255.255.255
    pool /Common/pool_x
    profiles {
        /Common/http { }
    }
    rules {
        /Common/rule_1
    }
    source-address-translation {
        pool /Common/snat_pool
        type snat
    }
}
""",
    ),
    (
        "f5_gtm",
        "F5",
        "gslb",
        """gtm datacenter DC1 { }
gtm server /Common/gtm-server1 {
    datacenter DC1
    monitor /Common/gtm_http
    product standard
}
gtm pool A /Common/gtm-pool {
    members {
        /Common/gtm-server:/Common/vs1 {
            member-order 1
        }
    }
    monitor /Common/gtm_http
    ttl 30
}
gtm wideip A www.example.com {
    pool-lb-mode round-robin
    pools {
        /Common/gtm-pool {
            order 1
        }
    }
}
""",
    ),
    (
        "a10_slb",
        "A10",
        "slb",
        """slb server server1 10.1.1.1
   port 80 tcp
slb service-group sg1 tcp
    method round-robin
slb virtual-server vs1 10.2.2.2
    port 80 tcp
       service-group sg1
""",
    ),
    (
        "maipu_switch",
        "Maipu",
        "switch",
        """vlan 10
 name users
interface GigabitEthernet0/1
 description uplink
 switchport mode access
 switchport access vlan 10
 switchport trunk allowed vlan 10,20
 ip address 10.0.0.1 255.255.255.0
 no shutdown
""",
    ),
    (
        "ruijie_switch",
        "Ruijie",
        "switch",
        """vlan 10
 name users
interface GigabitEthernet0/1
 description uplink
 switchport mode access
 switchport access vlan 10
 switchport trunk allowed vlan 10,20
 ip address 10.0.0.1 255.255.255.0
 no shutdown
""",
    ),
]


@pytest.mark.django_db
@pytest.mark.parametrize("cid,vendor,dtype,cfg", _INLINE, ids=[c[0] for c in _INLINE])
def test_inline_config_lands_in_db(cid, vendor, dtype, cfg):
    """内联配置端到端，判据同上：有产出有 Saver 必须入库 >0 行。

    A10 的全部顶层键（servers/service_groups/virtual_server）目前都在
    KNOWN_UNCONSUMED_PRODUCTS 里（无 Saver 是登记在案的缺口）——它验证的是
    「产出键没有出现新的未消费缺口」，而不是入库行数。
    """
    from ingest.mapping import canonical_key
    from ingest.parsers.contract import KNOWN_UNCONSUMED_PRODUCTS

    parsed = ParserFactory.get_parser_by_keys(vendor, dtype).parse(cfg)
    device = Device.objects.create(hostname=f"_t_inline_{cid}", device_type=dtype)
    payloads = build_saver_payloads(dtype, parsed)

    if not payloads:
        known = KNOWN_UNCONSUMED_PRODUCTS.get(dtype, set())
        produced = {canonical_key(k) for k, v in parsed.items() if v}
        assert produced and produced <= known, (
            f"{cid}: 产出 {sorted(produced)} 无任何 Saver，且不在 KNOWN_UNCONSUMED_PRODUCTS"
        )
        pytest.skip(f"{cid}: 全部产出键为登记在案的未消费缺口，无 Saver 可验")

    for saver, payload in payloads:
        created, updated = saver.save(device, payload)
        assert created + updated > 0, f"{cid}: {type(saver).__name__} 收到 {sorted(payload)} 却 0 行入库"


# ---------------------------------------------------------------------------
# 接口 enabled 三态：启用行 / 禁用行 / 无行（真机默认启用）
# ---------------------------------------------------------------------------

_H3C_STYLE = """interface GigabitEthernet1/0/1
 {up}
 ip address 10.0.0.1 255.255.255.0
interface GigabitEthernet1/0/2
 shutdown
 ip address 10.0.0.2 255.255.255.0
interface GigabitEthernet1/0/3
 ip address 10.0.0.3 255.255.255.0
"""


def _seven_line_cfg(up_line: str) -> str:
    """maipu / ruijie 的接口组是严格 7 行行序（description/switchport 系列必须给），
    三态各占一个接口：启用行 / 禁用行 / 无 shutdown 行。"""
    blocks = []
    for index, up in enumerate([up_line, "shutdown", ""], start=1):
        lines = [
            f"interface GigabitEthernet1/0/{index}",
            " description uplink",
            " switchport mode access",
            " switchport access vlan 10",
            " switchport trunk allowed vlan 10,20",
            f" ip address 10.0.0.{index} 255.255.255.0",
        ]
        if up:
            lines.append(f" {up}")
        blocks.append("\n".join(lines))
    return "\n".join(blocks) + "\n"


_ENABLED_CASES = [
    ("h3c", "H3C", _H3C_STYLE.format(up="undo shutdown")),
    ("huawei", "Huawei", _H3C_STYLE.format(up="undo shutdown")),
    ("maipu", "Maipu", _seven_line_cfg("no shutdown")),
    ("ruijie", "Ruijie", _seven_line_cfg("no shutdown")),
]


@pytest.mark.django_db
@pytest.mark.parametrize("cid,vendor,template", _ENABLED_CASES, ids=[c[0] for c in _ENABLED_CASES])
def test_interface_enabled_three_states(cid, vendor, template):
    """enabled 落库三态：启用行→True、禁用行→False、无行→True（默认启用）。

    **真实配置文件只有两态**（只落盘偏离默认的状态）：无行=启用、``shutdown``=禁用；
    ``undo/no shutdown`` 是改状态的命令、改完即消失、**不会出现在配置文件里**——
    第一个用例里的 undo/no shutdown 行是防御性覆盖（出现了也必须解析正确），真实
    输入是第二、三个接口的形态。

    历史 bug 链（2026-09 实测）：① 旧模板行 ``undo shutdown`` 在真实配置里是死分支
    （那行永不出现），实际恒走 default；② default 曾是 0（无行=禁用，与真机默认
    启用相反）；③ Saver 只认 int/float 且 ``enabled == 0`` 判向反转、``bool("0")``
    is True——三处叠加的结果是**接口永远存成启用**。此测试三态逐一断言，任何一环
    回退都会红。
    """
    from assets.models import Interface
    from ingest.savers.interface import InterfaceSaver

    parsed = ParserFactory.get_parser_by_keys(vendor, "switch").parse(template)
    device = Device.objects.create(hostname=f"_t_en_{cid}", device_type="switch")
    created, _ = InterfaceSaver().save(device, parsed)
    assert created == 3, f"{cid}: 只入库 {created}/3 个接口"

    state = {i.interface: i.enabled for i in Interface.objects.filter(device=device)}
    assert state["GigabitEthernet1/0/1"] is True, f"{cid}: 启用行接口存成了 {state['GigabitEthernet1/0/1']}"
    assert state["GigabitEthernet1/0/2"] is False, f"{cid}: 禁用行接口存成了启用（bool('0') 类 bug 回归）"
    assert state["GigabitEthernet1/0/3"] is True, f"{cid}: 无 shutdown 行应按真机默认启用"


@pytest.mark.django_db
def test_cisco_interface_shutdown_two_states():
    """cisco/ASA 的真实两态：禁用接口有 shutdown 行（惯例在 nameif 前）、启用接口无行。

    旧模板把 enabled 放在 ip address 之后的裸变量行，永远捕获不到位置在前部的
    shutdown 行——禁用接口恒存启用。修复：字面 ``shutdown`` 行插到 interface 之后
    （带 default(1) 使行可选），与四家交换机同款。
    """
    from assets.models import Interface
    from ingest.savers.interface import InterfaceSaver

    cfg = """interface GigabitEthernet0/0
 shutdown
 nameif outside
 security-level 0
 ip address 203.0.113.1 255.255.255.0
!
interface GigabitEthernet0/1
 nameif inside
 security-level 100
 ip address 10.0.0.1 255.255.255.0
!
"""
    parsed = ParserFactory.get_parser_by_keys("Cisco", "firewall").parse(cfg)
    device = Device.objects.create(hostname="_t_en_cisco", device_type="firewall")
    created, _ = InterfaceSaver().save(device, parsed)
    assert created == 2

    state = {i.interface: i.enabled for i in Interface.objects.filter(device=device)}
    assert state["GigabitEthernet0/0"] is False, "有 shutdown 行的接口应为禁用"
    assert state["GigabitEthernet0/1"] is True, "无行应按默认启用"
    # shutdown 行被正确消耗后，后续行序不乱（nameif 照常提取）。校验在解析层：
    # nameif 不落库——InterfaceSaver 不消费它（模板提取但 Saver 不读的字段）。
    rows = parsed.get("interfaces")
    rows = rows if isinstance(rows, list) else [rows]
    first = next(row for row in rows if row.get("interface") == "GigabitEthernet0/0")
    assert first.get("nameif") == "outside"
