"""资产域 MCP 工具测试（实体注册表 + 六个工具）。

四处约定：

- 工具是同步 def，SDK v2 在**工作线程**执行——主线程事务里的数据对其他数据库连接
  不可见，所以必须用 ``django_db(transaction=True)``（提交真数据、测后截断），普通 ``db``
  fixture 会让工具查不到夹具数据。
- 调用走 ``mcp.Client(server)`` 的内存传输，把「schema → 分发 → 工具 → 序列化」
  整条链跑通，而不是绕过 MCP 直调函数。
- 工具靠 ``import assets.mcp.tools`` 的副作用注册到根 server（与 asgi 的组合方式一致）
  ——只 import netops.mcp_server 拿到的是空 server。
- 断言打在**返回结构**上而不是内部函数上：实体注册表会持续加类型，工具签名必须稳定，
  测试盯着契约才不会一改 spec 就全红。
"""

import asyncio

import pytest
from mcp import Client

import assets.mcp.tools  # noqa: F401 — import 即注册（工具挂到 netops.mcp_server.mcp 上）
from assets.models import (
    ArpMac,
    Device,
    DeviceGroup,
    DeviceGroupMember,
    DeviceModel,
    Interface,
    IPAddress,
    Vendor,
    Vlan,
)
from netops.mcp_server import mcp as netops_mcp

pytestmark = pytest.mark.django_db(transaction=True)


def _call_tool(name: str, arguments: dict):
    async def _run():
        async with Client(netops_mcp) as client:
            return await client.call_tool(name, arguments)

    return asyncio.run(_run())


def _data(result) -> dict:
    """SDK v2 对 dict 注解的工具返回结构化内容。"""
    assert result.is_error is False, f"工具意外报错：{result.content[0].text}"
    return result.structured_content


def _error(result) -> str:
    assert result.is_error is True, "期望工具报错，实际成功返回"
    return result.content[0].text


def _make_device(hostname: str, device_type: str = "switch", **kwargs) -> Device:
    return Device.objects.create(hostname=hostname, device_type=device_type, **kwargs)


# ---------------------------------------------------------------------------
# find
# ---------------------------------------------------------------------------


def test_find_returns_candidates_across_types():
    """同一个串命中两类实体时，两类都要返回——判断权交给调用方。"""
    _make_device("NET-FW01", "firewall", ip_address="10.0.1.5")
    IPAddress.objects.create(ip_address="10.0.1.5", status="used", description="防火墙管理口")

    data = _data(_call_tool("find", {"q": "10.0.1.5"}))

    assert data["hint"] == "ip"
    types = {item["entity_type"] for item in data["candidates"]}
    assert {"device", "ip_address"} <= types
    # 完全相等的一律 score=3
    assert all(item["score"] == 3 for item in data["candidates"])
    assert data["candidates"][0]["summary"].get("hostname") or data["candidates"][0]["summary"].get("ip_address")


def test_find_normalizes_mac_separators():
    """ARP 表存原始串，三种分隔符写法都要能命中。"""
    device = _make_device("NET-SW01", "switch", ip_address="10.0.0.2")
    ArpMac.objects.create(device=device, ip_address="10.0.0.99", mac_address="aa:bb:cc:dd:ee:ff")

    for text in ("AA-BB-CC-DD-EE-FF", "aabbccddeeff", "aabb.ccdd.eeff"):
        data = _data(_call_tool("find", {"q": text}))
        assert data["hint"] == "mac"
        assert any(item["entity_type"] == "arp_mac" for item in data["candidates"]), text


def test_find_rejects_unknown_type():
    assert "未知的 entity_type" in _error(_call_tool("find", {"q": "x", "types": "docker"}))


# ---------------------------------------------------------------------------
# list_records
# ---------------------------------------------------------------------------


def test_list_records_filter_pagination_and_summary():
    vendor = Vendor.objects.create(name="Huawei")
    model = DeviceModel.objects.create(name="CE6865", vendor=vendor)
    _make_device("NET-HW01", "switch", device_model=model)
    _make_device("NET-RJ01", "switch")
    _make_device("NET-FW01", "firewall")

    data = _data(_call_tool("list_records", {"entity_type": "device", "filters": {"device_type": "switch"}}))
    assert data["total"] == 2
    assert {row["hostname"] for row in data["rows"]} == {"NET-HW01", "NET-RJ01"}
    # 摘要层不带 remark/created_at 这类长字段
    assert "remark" not in data["rows"][0]

    data = _data(
        _call_tool(
            "list_records",
            {"entity_type": "device", "filters": {"vendor": "huawei"}, "detail": True},
        )
    )
    assert data["total"] == 1
    assert data["rows"][0]["hostname"] == "NET-HW01"
    assert "created_at" in data["rows"][0]

    data = _data(_call_tool("list_records", {"entity_type": "device", "page": 2, "page_size": 2}))
    assert data["total"] == 3
    assert data["returned"] == 1
    assert data["truncated"] is False


def test_list_records_rejects_unknown_filter():
    """未声明的过滤键必须报错——静默忽略会让调用方误以为过滤生效。"""
    _make_device("NET-SW01", "switch")
    message = _error(_call_tool("list_records", {"entity_type": "device", "filters": {"os_version": "9"}}))
    assert "不支持的过滤字段" in message
    assert "device_type" in message  # 错误里要带可用值


def test_list_records_rejects_bad_pagination_and_order():
    assert "page_size" in _error(_call_tool("list_records", {"entity_type": "device", "page_size": 500}))
    assert "不支持按" in _error(_call_tool("list_records", {"entity_type": "device", "order": "remark"}))


def test_list_records_applies_requested_order():
    """order 必须真正覆盖 spec 的默认排序，不能只校验不生效（静默给错顺序最坑）。"""
    first = _make_device("NET-A01", "switch")
    second = _make_device("NET-B01", "switch")
    Interface.objects.create(device=first, interface="Zif", mode="access")
    Interface.objects.create(device=second, interface="Aif", mode="access")

    default = _data(_call_tool("list_records", {"entity_type": "interface", "filters": {"mode": "access"}}))
    assert [row["interface"] for row in default["rows"]] == ["Zif", "Aif"]  # device__hostname, interface

    ordered = _data(_call_tool("list_records", {"entity_type": "interface", "filters": {"mode": "access"}, "order": "interface"}))
    assert [row["interface"] for row in ordered["rows"]] == ["Aif", "Zif"]


# ---------------------------------------------------------------------------
# get_record / bundle
# ---------------------------------------------------------------------------


def test_get_record_device_include_groups_keeps_role():
    """角色在 membership 上，不能因为走组的序列化器就丢掉。"""
    device = _make_device("NET-FW01", "firewall")
    group = DeviceGroup.objects.create(name="fw-ha", group_type="ha")
    DeviceGroupMember.objects.create(group=group, device=device, device_role="master")

    data = _data(_call_tool("get_record", {"entity_type": "device", "key": "net-fw01", "include": "groups"}))

    assert data["record"]["hostname"] == "NET-FW01"  # 业务键大小写不敏感
    rows = data["relations"]["groups"]["rows"]
    assert rows[0]["name"] == "fw-ha"
    assert rows[0]["group_type_display"] == "主备"
    assert rows[0]["device_role"] == "master"


def test_get_record_scoped_types_require_device():
    device = _make_device("NET-SW01", "switch")
    Interface.objects.create(device=device, interface="Gi1/0/1", mode="access")

    message = _error(_call_tool("get_record", {"entity_type": "interface", "key": "Gi1/0/1"}))
    assert "device 参数" in message

    data = _data(_call_tool("get_record", {"entity_type": "interface", "key": "Gi1/0/1", "device": "NET-SW01"}))
    assert data["record"]["interface"] == "Gi1/0/1"
    assert data["record"]["device_hostname"] == "NET-SW01"


def test_get_record_numeric_key_beats_primary_key():
    """VLAN 的 vid 是数字业务键：key=<数字> 必须命中 vid，而不是同号主键那条。

    构造方式不依赖自增序列：先建一条「主键 = X、vid 是别的值」的记录，再把另一条的
    vid 设成 X，于是同一个数字既是主键又是业务键，两者指向不同记录。
    """
    device = _make_device("NET-SW01", "switch")
    wrong = Vlan.objects.create(device=device, vid=999999)  # 主键 X，业务键不是 X
    wanted = Vlan.objects.create(device=device, vid=1)
    wanted.vid = wrong.pk
    wanted.save(update_fields=["vid"])

    data = _data(_call_tool("get_record", {"entity_type": "vlan", "key": str(wrong.pk), "device": "NET-SW01"}))

    assert data["record"]["vid"] == wrong.pk  # 命中 wanted；按主键取会拿到 vid=999999 那条


def test_get_record_missing_and_bad_include():
    _make_device("NET-SW01", "switch")
    assert "不存在" in _error(_call_tool("get_record", {"entity_type": "device", "key": "nope"}))
    assert "不支持 include" in _error(
        _call_tool("get_record", {"entity_type": "device", "key": "NET-SW01", "include": "cabinets"})
    )


def test_bundle_returns_profile_and_default_sections():
    device = _make_device("NET-FW01", "firewall", ip_address="10.0.1.5")
    Interface.objects.create(device=device, interface="Gi1/0/1", mode="access")
    ArpMac.objects.create(device=device, ip_address="10.0.1.9", mac_address="aa:bb:cc:dd:ee:01")
    IPAddress.objects.create(ip_address="10.0.1.5", status="used", device=device)

    data = _data(_call_tool("bundle", {"entity_type": "device", "key": "NET-FW01"}))

    assert data["profile"]["hostname"] == "NET-FW01"
    # 默认段固定给全，组里没数据也给空段——缺段会让调用方以为「这台设备没有组」
    assert set(data["sections"]) == {"groups", "interfaces", "ip_addresses", "arp"}
    assert data["sections"]["groups"]["total"] == 0
    assert data["sections"]["interfaces"]["total"] == 1
    assert data["sections"]["arp"]["rows"][0]["mac_address"] == "aa:bb:cc:dd:ee:01"


# ---------------------------------------------------------------------------
# relations
# ---------------------------------------------------------------------------


def test_relations_down_and_type_filter():
    device = _make_device("NET-SW01", "switch")
    Interface.objects.create(device=device, interface="Gi1/0/1", mode="access")
    Interface.objects.create(device=device, interface="Gi1/0/2", mode="trunk")
    ArpMac.objects.create(device=device, ip_address="10.0.0.9", mac_address="aa:bb:cc:dd:ee:02")

    data = _data(_call_tool("relations", {"entity_type": "device", "key": "NET-SW01", "types": "interface"}))
    assert [node["key"] for node in data["nodes"][1:]] == ["Gi1/0/1", "Gi1/0/2"]
    assert len(data["edges"]) == 2
    assert data["truncated"] is False


def test_relations_up_from_ip_reaches_device():
    """反向边就是影响面：这个地址被哪台设备观测到。"""
    device = _make_device("NET-SW01", "switch")
    ArpMac.objects.create(device=device, ip_address="10.0.0.9", mac_address="aa:bb:cc:dd:ee:03")

    rows = _data(_call_tool("list_records", {"entity_type": "arp_mac", "filters": {"keyword": "10.0.0.9"}}))
    arp_id = rows["rows"][0]["id"]

    data = _data(_call_tool("relations", {"entity_type": "arp_mac", "key": str(arp_id), "direction": "up"}))
    assert any(node["entity_type"] == "device" and node["key"] == "NET-SW01" for node in data["nodes"])


def test_relations_limit_sets_truncated():
    device = _make_device("NET-SW01", "switch")
    for index in range(5):
        Interface.objects.create(device=device, interface=f"Gi1/0/{index}", mode="access")

    data = _data(_call_tool("relations", {"entity_type": "device", "key": "NET-SW01", "limit": 3}))
    assert data["truncated"] is True
    assert len(data["nodes"]) == 3


def test_relations_rejects_bad_direction_and_depth():
    _make_device("NET-SW01", "switch")
    assert "direction" in _error(_call_tool("relations", {"entity_type": "device", "key": "NET-SW01", "direction": "sideways"}))
    assert "depth" in _error(_call_tool("relations", {"entity_type": "device", "key": "NET-SW01", "depth": 9}))


# ---------------------------------------------------------------------------
# locate
# ---------------------------------------------------------------------------


def test_locate_flags_unregistered_online_address():
    device = _make_device("NET-SW01", "switch")
    ArpMac.objects.create(device=device, ip_address="10.0.9.9", mac_address="aa:bb:cc:dd:ee:04", interface="Gi1/0/8")

    data = _data(_call_tool("locate", {"target": "10.0.9.9"}))

    assert data["registry"] is None
    assert data["observations"][0]["port"] == "Gi1/0/8"
    assert any("未在 IPAddress 中登记" in item for item in data["conflicts"])


def test_locate_flags_mac_mismatch_across_devices():
    first = _make_device("NET-SW01", "switch")
    second = _make_device("NET-SW02", "switch")
    ArpMac.objects.create(device=first, ip_address="10.0.9.9", mac_address="aa:bb:cc:dd:ee:05", interface="Gi1/0/1")
    ArpMac.objects.create(device=second, ip_address="10.0.9.9", mac_address="aa:bb:cc:dd:ee:06", interface="Gi1/0/1")

    data = _data(_call_tool("locate", {"target": "10.0.9.9"}))
    assert any("同一地址对应 2 个不同 MAC" in item for item in data["conflicts"])
    assert data["observed_total"] == 2


def test_locate_rejects_network_input():
    assert "只接受单个地址" in _error(_call_tool("locate", {"target": "10.0.0.0/24"}))


def test_locate_matches_interface_ip_by_token():
    """查 10.0.1.5 不能把 10.0.1.50 的接口台账一起捞回来（子串匹配会假阳性）。"""
    device = _make_device("NET-SW01", "switch")
    Interface.objects.create(device=device, interface="Gi1/0/1", ip_address="10.0.1.5/24")
    Interface.objects.create(device=device, interface="Gi1/0/2", ip_address="10.0.1.50")
    ArpMac.objects.create(device=device, ip_address="10.0.1.5", mac_address="aa:bb:cc:dd:ee:07")

    data = _data(_call_tool("locate", {"target": "10.0.1.5"}))

    assert [row["interface"] for row in data["interfaces"]] == ["Gi1/0/1"]
