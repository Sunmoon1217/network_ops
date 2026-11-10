"""注册机制：实体/边登记、重复检测、视图（queryset_provider）注册。

注册表是进程级全局状态，测试只登记/注销自己的临时类型，不碰资产域已注册的 12 个类型。
"""

import asyncio

import pytest
from mcp import Client

import assets.mcp.tools  # noqa: F401 — 注册通用工具 + 资产实体 + locate
from assets import models
from assets.serializers import views as s
from core.mcp.registry import SPEC, Edge, EntitySpec, Filter, register_edge, register_entity, unregister_entity
from core.mcp.server import mcp as netops_mcp

pytestmark = pytest.mark.django_db(transaction=True)

NODE_TYPE = "test_device_view"


def _call_tool(name: str, arguments: dict):
    async def _run():
        async with Client(netops_mcp) as client:
            return await client.call_tool(name, arguments)

    return asyncio.run(_run())


def _data(result) -> dict:
    assert result.is_error is False, f"工具意外报错：{result.content[0].text}"
    return result.structured_content


def _view_spec() -> EntitySpec:
    """没有 model、只有 queryset_provider 的「视图」实体。"""
    return EntitySpec(
        node_type=NODE_TYPE,
        label="测试视图",
        serializer=s.DeviceSerializer,
        key="hostname",
        summary=("hostname", "device_type"),
        queryset_provider=lambda: models.Device.objects.filter(device_type="switch"),
        filters={"keyword": Filter(("hostname",))},
        order=("hostname",),
    )


def test_register_entity_and_duplicate_guard():
    spec = _view_spec()
    register_entity(spec)
    try:
        assert SPEC[NODE_TYPE] is spec
        with pytest.raises(ValueError, match="已注册"):
            register_entity(_view_spec())

        replacement = _view_spec()
        register_entity(replacement, override=True)
        assert SPEC[NODE_TYPE] is replacement
    finally:
        unregister_entity(NODE_TYPE)

    assert NODE_TYPE not in SPEC


def test_register_edge_requires_registered_endpoints():
    edge = Edge(name="x", src="nope_a", dst="nope_b", forward=lambda obj: [], reverse=lambda obj: [])
    with pytest.raises(ValueError, match="端点未注册"):
        register_edge(edge)


def test_view_registration_is_queryable():
    """视图实体没有 model，query 的路径校验跳过，但白名单与 provider 仍然生效。"""
    models.Device.objects.create(hostname="NET-SW01", device_type="switch")
    models.Device.objects.create(hostname="NET-FW01", device_type="firewall")
    register_entity(_view_spec())
    try:
        data = _data(_call_tool("query", {"plan": {"entity_type": NODE_TYPE, "limit": 10}}))
        assert data["total"] == 1
        assert data["rows"][0]["hostname"] == "NET-SW01"
    finally:
        unregister_entity(NODE_TYPE)
