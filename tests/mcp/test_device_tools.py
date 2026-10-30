"""设备库 MCP 工具测试。

两处约定：
- 工具是同步 def，SDK v2 在**工作线程**执行——主线程事务里的数据对其他数据库连接
  不可见，所以必须用 ``django_db(transaction=True)``（提交真数据、测后截断），
  普通 ``db`` fixture 会让工具查不到夹具数据。
- 调用走 ``mcp.Client(server)`` 的内存传输，把「schema → 分发 → 工具 → 序列化」
  整条链跑通，而不是绕过 MCP 直调函数。
"""

import asyncio

import pytest
from mcp import Client

from assets.models import Device, DeviceGroup, DeviceGroupMember, DeviceModel, Vendor
from netops.mcp_server import mcp as netops_mcp

pytestmark = pytest.mark.django_db(transaction=True)


def _call_tool(name: str, arguments: dict):
    async def _run():
        async with Client(netops_mcp) as client:
            return await client.call_tool(name, arguments)

    return asyncio.run(_run())


def _make_device(hostname: str, device_type: str = "switch", **kwargs) -> Device:
    return Device.objects.create(hostname=hostname, device_type=device_type, **kwargs)


def test_search_devices_keyword_and_type_filter():
    _make_device("NET-FW01", "firewall", ip_address="10.0.0.1")
    _make_device("NET-SW01", "switch", ip_address="10.0.0.2")

    result = _call_tool("search_devices", {"keyword": "FW"})
    assert result.is_error is False
    data = result.structured_content
    assert data["total"] == 1
    assert data["devices"][0]["hostname"] == "NET-FW01"
    assert data["devices"][0]["device_type_display"] == "防火墙"

    result = _call_tool("search_devices", {"device_type": "switch"})
    assert result.structured_content["total"] == 1
    assert result.structured_content["devices"][0]["hostname"] == "NET-SW01"


def test_search_devices_vendor_filter_and_pagination():
    vendor = Vendor.objects.create(name="Huawei")
    model = DeviceModel.objects.create(name="CE6865", vendor=vendor)
    _make_device("NET-HW01", "switch", device_model=model)
    _make_device("NET-RJ01", "switch")

    result = _call_tool("search_devices", {"vendor": "huawei"})
    data = result.structured_content
    assert data["total"] == 1
    assert data["devices"][0]["hostname"] == "NET-HW01"

    result = _call_tool("search_devices", {"page_size": 1, "page": 2})
    data = result.structured_content
    assert data["total"] == 2
    assert len(data["devices"]) == 1
    assert data["devices"][0]["hostname"] == "NET-RJ01"  # 按主机名排序的第二页


def test_search_devices_invalid_params_raise_tool_error():
    result = _call_tool("search_devices", {"device_type": "switchs"})
    assert result.is_error is True
    assert "device_type" in result.content[0].text

    result = _call_tool("search_devices", {"page_size": 0})
    assert result.is_error is True
    assert "page_size" in result.content[0].text


def test_get_device_detail_includes_groups():
    device = _make_device("NET-FW01", "firewall", ip_address="10.0.0.1")
    group = DeviceGroup.objects.create(name="fw-ha", group_type="ha")
    DeviceGroupMember.objects.create(group=group, device=device, device_role="master")

    # 主机名大小写不敏感
    result = _call_tool("get_device", {"hostname": "net-fw01"})
    assert result.is_error is False
    data = result.structured_content
    assert data["device"]["hostname"] == "NET-FW01"
    assert data["groups"] == [{"group_name": "fw-ha", "group_type": "ha", "group_type_display": "主备", "device_role": "master"}]


def test_get_device_missing_raises_tool_error():
    result = _call_tool("get_device", {"hostname": "NOT-EXIST"})
    assert result.is_error is True
    assert "设备不存在" in result.content[0].text


def test_list_device_groups_includes_members():
    device = _make_device("NET-FW01", "firewall")
    group = DeviceGroup.objects.create(name="fw-ha", group_type="ha", description="防火墙主备")
    DeviceGroupMember.objects.create(group=group, device=device, device_role="backup")
    DeviceGroup.objects.create(name="core-stack", group_type="stack")

    result = _call_tool("list_device_groups", {"keyword": "fw"})
    data = result.structured_content
    assert data["total"] == 1
    assert data["groups"][0]["name"] == "fw-ha"
    assert data["groups"][0]["group_type_display"] == "主备"
    assert data["groups"][0]["members"] == [{"hostname": "NET-FW01", "device_role": "backup"}]

    result = _call_tool("list_device_groups", {})
    assert result.structured_content["total"] == 2
