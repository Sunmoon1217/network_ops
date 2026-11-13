"""统一配置项与软资产（T1 / T4）的 MCP 契约测试。

锁住三件事：六个新节点已注册并可按业务键取单条；软资产的部署/证据边能走通
（域名 → LB 服务 / wideip / 设备，LB → 配置行）；扩展表以行 id 为键、`ci_id` 出现在摘要里。
"""

import asyncio

import pytest
from mcp import Client

import llmtools  # noqa: F401 — 包初始化即接线：注册资产实体 + 全部工具
from assets.models import (
    CIType,
    ConfigurationItem,
    Device,
    DomainAsset,
    GtmWideip,
    LoadBalancerService,
    LtmVirtualServer,
    PhysicalServer,
)
from llmtools import mcpserver as netops_mcp
from llmtools.registry import SPEC

pytestmark = pytest.mark.django_db(transaction=True)


def _call_tool(name: str, arguments: dict):
    async def _run():
        async with Client(netops_mcp) as client:
            return await client.call_tool(name, arguments)

    return asyncio.run(_run())


def _data(result) -> dict:
    assert result.is_error is False, f"工具意外报错：{result.content[0].text}"
    return result.structured_content


def _ci(ci_type: str, name: str) -> ConfigurationItem:
    return ConfigurationItem.objects.create(ci_type=ci_type, name=name)


def test_six_asset_nodes_are_registered():
    """T1 的四类扩展与 T4 的两张软资产表都要能被 MCP 查询。"""
    expected = {
        "physical_server",
        "virtual_machine",
        "database_instance",
        "application_service",
        "domain",
        "load_balancer_service",
    }
    assert expected <= set(SPEC)


def test_get_domain_by_fqdn():
    ci = _ci(CIType.DOMAIN, "app.example.com")
    DomainAsset.objects.create(ci=ci, fqdn="app.example.com", devices=["SW-01"], vips=["1.2.3.4#80"])

    data = _data(_call_tool("get_record", {"entity_type": "domain", "key": "app.example.com"}))
    assert data["fqdn"] == "app.example.com"
    assert data["ci_id"] == ci.ci_id


def test_get_lb_service_by_asset_key():
    ci = _ci(CIType.LOAD_BALANCER_SERVICE, "1.2.3.4#80")
    LoadBalancerService.objects.create(ci=ci, asset_key="1.2.3.4#80", vip="1.2.3.4", port="80", devices=["SW-01"])

    data = _data(_call_tool("get_record", {"entity_type": "load_balancer_service", "key": "1.2.3.4#80"}))
    assert data["asset_key"] == "1.2.3.4#80"
    assert data["ci_id"] == ci.ci_id


def test_get_physical_server_by_row_id():
    """扩展表 hostname 不唯一，业务键用行 id；`ci_id` 必须出现在摘要里。"""
    ci = _ci(CIType.PHYSICAL_SERVER, "host-a")
    ps = PhysicalServer.objects.create(ci=ci, hostname="host-a", mgmt_ip="10.0.0.9")

    data = _data(_call_tool("get_record", {"entity_type": "physical_server", "key": str(ps.id)}))
    assert data["ci_id"] == ci.ci_id
    assert data["hostname"] == "host-a"


def test_domain_down_relations_reach_lb_wideip_and_devices():
    """域名沿三条边展开：LB 服务（VIP 归一）、wideip（证据链）、部署设备。"""
    device = Device.objects.create(hostname="SW-01", device_type="slb")
    domain_ci = _ci(CIType.DOMAIN, "app.example.com")
    DomainAsset.objects.create(ci=domain_ci, fqdn="app.example.com", devices=["SW-01"], vips=["1.2.3.4#80"])
    GtmWideip.objects.create(device=device, name="app.example.com", rtype="A", lb_mode="global", pools=["pool_web"])
    lb_ci = _ci(CIType.LOAD_BALANCER_SERVICE, "1.2.3.4#80")
    LoadBalancerService.objects.create(ci=lb_ci, asset_key="1.2.3.4#80", vip="1.2.3.4", port="80", devices=["SW-01"])

    data = _data(_call_tool("relations", {"entity_type": "domain", "key": "app.example.com", "direction": "down"}))
    types = {node["entity_type"] for node in data["nodes"]}
    assert {"load_balancer_service", "gtm_wideip", "device"} <= types
    relations = {edge["relation"] for edge in data["edges"]}
    assert {"load_balancer_services", "wideips", "devices"} <= relations


def test_lb_up_relations_reach_domain():
    """影响面反向：从 LB 服务往上能看到承载它的域名资产。"""
    lb_ci = _ci(CIType.LOAD_BALANCER_SERVICE, "1.2.3.4#80")
    LoadBalancerService.objects.create(ci=lb_ci, asset_key="1.2.3.4#80", vip="1.2.3.4", port="80")
    domain_ci = _ci(CIType.DOMAIN, "app.example.com")
    DomainAsset.objects.create(ci=domain_ci, fqdn="app.example.com", vips=["1.2.3.4#80"])

    data = _data(_call_tool("relations", {"entity_type": "load_balancer_service", "key": "1.2.3.4#80", "direction": "up"}))
    types = {node["entity_type"] for node in data["nodes"]}
    assert "domain" in types


def test_lb_evidence_edge_reaches_ltm_virtual_server():
    """证据链：LB 服务 → 各设备上的 LTM 虚拟服务器配置行。"""
    device = Device.objects.create(hostname="FW-01", device_type="firewall")
    lb_ci = _ci(CIType.LOAD_BALANCER_SERVICE, "1.2.3.4#80")
    LoadBalancerService.objects.create(ci=lb_ci, asset_key="1.2.3.4#80", vip="1.2.3.4", port="80")
    LtmVirtualServer.objects.create(device=device, name="vs_web", vs_address="1.2.3.4", vs_port="80", protocol="tcp", status="enabled", pool="pool_web")

    data = _data(
        _call_tool(
            "relations",
            {"entity_type": "load_balancer_service", "key": "1.2.3.4#80", "direction": "down", "types": "ltm_virtual_server"},
        )
    )
    types = {node["entity_type"] for node in data["nodes"]}
    assert "ltm_virtual_server" in types
    assert {edge["relation"] for edge in data["edges"]} == {"virtual_servers"}
