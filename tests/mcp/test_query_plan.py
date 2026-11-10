"""结构化查询工具（query）：白名单、AND/OR、排序、投影、分页。

与 ``test_entity_tools.py`` 同一套约定：``django_db(transaction=True)``（工具在
工作线程执行，看不到主线程未提交的数据）、走 ``mcp.Client`` 内存传输、断言打在
返回结构上。
"""

import asyncio

import pytest
from mcp import Client

import assets.mcp.tools  # noqa: F401 — import 即注册（工具挂到 netops.mcp_server.mcp 上）
from assets.models import Device, DeviceModel, Vendor
from netops.mcp_server import mcp as netops_mcp

pytestmark = pytest.mark.django_db(transaction=True)


def _call_tool(name: str, arguments: dict):
    async def _run():
        async with Client(netops_mcp) as client:
            return await client.call_tool(name, arguments)

    return asyncio.run(_run())


def _data(result) -> dict:
    assert result.is_error is False, f"工具意外报错：{result.content[0].text}"
    return result.structured_content


def _error(result) -> str:
    assert result.is_error is True, "期望工具报错，实际成功返回"
    return result.content[0].text


def _make_device(hostname: str, device_type: str = "switch", **kwargs) -> Device:
    return Device.objects.create(hostname=hostname, device_type=device_type, **kwargs)


def test_query_and_filters_order_projection_and_offset():
    """多跳过滤 + AND + 倒序 + 投影 + offset 一起生效。"""
    vendor = Vendor.objects.create(name="Huawei")
    model = DeviceModel.objects.create(name="CE6865", vendor=vendor)
    _make_device("NET-HW01", "switch", device_model=model, ip_address="10.0.0.11")
    _make_device("NET-HW02", "switch", device_model=model, ip_address="10.0.0.12")
    _make_device("NET-FW01", "firewall", ip_address="10.0.0.21")

    data = _data(
        _call_tool(
            "query",
            {
                "plan": {
                    "entity_type": "device",
                    "filters": [
                        {"field": "device_type", "op": "exact", "value": "switch"},
                        {"field": "device_model__vendor__name", "op": "iexact", "value": "huawei"},
                    ],
                    "order_by": [{"field": "hostname", "direction": "desc"}],
                    "fields": ["hostname", "ip_address"],
                    "limit": 1,
                    "offset": 1,
                }
            },
        )
    )

    assert data["total"] == 2
    assert data["returned"] == 1
    # offset=1 + 1 条刚好取完，不算截断
    assert data["truncated"] is False
    assert data["rows"] == [{"hostname": "NET-HW01", "ip_address": "10.0.0.11"}]
    assert data["plan"]["logic"] == "and"


def test_query_or_logic_and_in_operator():
    _make_device("NET-SW01", "switch")
    _make_device("NET-SW02", "switch")
    _make_device("NET-FW01", "firewall")
    _make_device("NET-RT01", "router")

    data = _data(
        _call_tool(
            "query",
            {
                "plan": {
                    "entity_type": "device",
                    "filters": [
                        {"field": "hostname", "op": "in", "value": ["NET-SW01", "NET-FW01", "NET-RT01"]},
                        {"field": "device_type", "op": "exact", "value": "router"},
                    ],
                    "logic": "or",
                }
            },
        )
    )

    assert data["total"] == 3
    assert {row["hostname"] for row in data["rows"]} == {"NET-SW01", "NET-FW01", "NET-RT01"}


def test_query_default_is_summary_and_star_returns_full():
    _make_device("NET-SW01", "switch", remark="rack A")

    summary = _data(_call_tool("query", {"plan": {"entity_type": "device", "limit": 1}}))
    assert "remark" not in summary["rows"][0]

    full = _data(_call_tool("query", {"plan": {"entity_type": "device", "fields": ["*"], "limit": 1}}))
    assert full["rows"][0]["remark"] == "rack A"


def test_query_rejects_unknown_field_and_operator():
    _make_device("NET-SW01", "switch")

    message = _error(_call_tool("query", {"plan": {"entity_type": "device", "filters": [{"field": "os_version", "value": "9"}]}}))
    assert "不支持按" in message
    assert "device_type" in message  # 错误里要带可用路径

    message = _error(
        _call_tool(
            "query",
            {"plan": {"entity_type": "device", "filters": [{"field": "hostname", "op": "regex", "value": "x"}]}},
        )
    )
    assert "不支持操作符" in message


def test_query_rejects_unknown_plan_key_and_bad_limit():
    message = _error(_call_tool("query", {"plan": {"entity_type": "device", "raw_sql": "select 1"}}))
    assert "未声明字段" in message

    message = _error(_call_tool("query", {"plan": {"entity_type": "device", "limit": 500}}))
    assert "limit" in message


def test_query_rejects_projection_outside_summary():
    message = _error(_call_tool("query", {"plan": {"entity_type": "device", "fields": ["remark"]}}))
    assert "不能投影字段" in message
