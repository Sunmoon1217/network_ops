"""互联网资产分析 xlsx 导出测试。

导出用后端的 openpyxl 生成，前端不引入 xlsx 依赖；这里验证响应头、工作簿内容
以及摊平后的层级结构。
"""

from io import BytesIO

import pytest
from openpyxl import load_workbook

from assets.api.analysis import flatten_asset_rows
from assets.models import (
    Device,
    GtmPool,
    GtmServer,
    GtmVServer,
    GtmWideip,
    LtmPool,
    LtmPoolMember,
    LtmVirtualServer,
)

EXPORT_URL = "/api/assets/internet-analysis/export/"


def _device(hostname: str, device_type: str = "gslb") -> Device:
    return Device.objects.create(hostname=hostname, device_type=device_type)


def _wideip(device: Device, name: str, pools: list[str]) -> GtmWideip:
    return GtmWideip.objects.create(device=device, name=name, rtype="A", lb_mode="round-robin", pools=pools)


def _gtm_pool(device: Device, name: str, members: list) -> GtmPool:
    return GtmPool.objects.create(device=device, name=name, members=members)


def _gtm_vserver(device: Device, server_name: str, vs_name: str, ip: str, port: str) -> GtmVServer:
    server, _ = GtmServer.objects.get_or_create(device=device, name=server_name)
    return GtmVServer.objects.create(device=device, server=server, name=vs_name, ip_address=ip, port=port)


def _ltm_virtual(device: Device, name: str, ip: str, port: str, pool: str = "") -> LtmVirtualServer:
    return LtmVirtualServer.objects.create(device=device, name=name, vs_address=ip, vs_port=port, pool=pool)


def _build_resolved_chain(hostname: str = "ia-exp") -> Device:
    """搭一条能完整解析到后端成员的链路"""
    gslb = _device(hostname)
    _wideip(gslb, "www.example.com", ["pool_web"])
    _gtm_pool(gslb, "pool_web", [{"server_name": "s1", "vs_name": "vs1"}])
    _gtm_vserver(gslb, "s1", "vs1", "10.1.1.1", "80")

    ltm = _device(f"{hostname}-ltm", "slb")
    _ltm_virtual(ltm, "vs_web", "10.1.1.1", "80", pool="pool_backend")
    LtmPool.objects.create(device=ltm, name="pool_backend", mode="http")
    LtmPoolMember.objects.create(pool_name="pool_backend", name="m1", address="10.9.9.9", port="8080")
    return gslb


@pytest.mark.django_db
def test_flatten_rows_cover_every_level():
    """摊平结果应包含 WideIP → Pool → Member → GTM VS → LTM VS → Pool Member"""
    from assets.api.analysis import analyze_device

    gslb = _build_resolved_chain("ia-flat")
    rows = flatten_asset_rows(analyze_device(gslb))

    assert [row["kind"] for row in rows] == ["wideip", "pool", "member", "vserver", "ltm_vs", "ltm_member"]
    assert [row["depth"] for row in rows] == [0, 1, 2, 3, 3, 4]
    # 没有下级虚拟服务器的成员是链路终点
    assert rows[-1]["is_final"] is True


@pytest.mark.django_db
def test_export_returns_xlsx_workbook():
    from django.test import Client

    gslb = _build_resolved_chain("ia-xlsx")

    res = Client().get(EXPORT_URL, {"device": gslb.pk})

    assert res.status_code == 200
    assert res["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "attachment" in res["Content-Disposition"]
    assert "ia-xlsx" in res["Content-Disposition"]

    sheet = load_workbook(BytesIO(res.content)).active
    assert sheet.title == "互联网资产分析"
    assert [cell.value for cell in sheet[1]] == ["层级 / 对象", "名称", "地址 / 端口", "LTM 设备", "状态", "说明"]

    first_column = [sheet.cell(row=index, column=1).value for index in range(2, sheet.max_row + 1)]
    assert any(value and value.strip() == "WideIP" for value in first_column)
    assert any(value and value.strip() == "LTM VS" for value in first_column)
    # 第二层及以后用空格缩进
    assert any(value and value.startswith("    ") for value in first_column)


@pytest.mark.django_db
def test_export_requires_device_param():
    from django.test import Client

    assert Client().get(EXPORT_URL).status_code == 400


@pytest.mark.django_db
def test_export_unknown_device_returns_404():
    from django.test import Client

    assert Client().get(EXPORT_URL, {"device": 999999}).status_code == 404
