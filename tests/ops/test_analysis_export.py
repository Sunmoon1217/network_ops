"""互联网资产分析链路的扁平列与 xlsx 导出测试。

列结构固定为：GTM 四列（域名 / 类型 / GTM VS 的 IP / 端口）
+ LTM 两级各四列（LLB、SLB 的虚拟服务器与后端成员）+ 说明。

注意 LTM 的两级不是数据库外键关系：GTM 虚拟服务器的 ip:port 命中某个
LtmVirtualServer 即为 LLB，LLB 池成员的 address:port 再命中一个 LtmVirtualServer
即为 SLB。所以测试要造出能"命中"的地址。
"""

from io import BytesIO

import pytest
from django.test import Client
from openpyxl import load_workbook

from assets.models import (
    Device,
    GtmPool,
    GtmServer,
    GtmVServer,
    GtmWideip,
    LtmPool,
    LtmPoolMember,
    LtmVirtualServer,
    ServerOwner,
)
from ops.api.analysis import EXPORT_COLUMN_WIDTHS, EXPORT_HEADERS, analyze_device, build_path_rows

EXPORT_URL = "/api/internet-analysis/export/"
ANALYZE_URL = "/api/internet-analysis/analyze/"


def _analyze(device) -> None:
    """触发一次分析，把结果写进缓存（导出接口只读缓存）"""
    res = Client().post(f"{ANALYZE_URL}?device={device.pk}")
    assert res.status_code == 200, res.content


def _device(hostname: str, device_type: str = "gslb") -> Device:
    return Device.objects.create(hostname=hostname, device_type=device_type)


def _wideip(device: Device, name: str, pools: list[str]) -> GtmWideip:
    return GtmWideip.objects.create(device=device, name=name, rtype="A", lb_mode="round-robin", pools=pools)


def _gtm_pool(device: Device, name: str, members: list) -> GtmPool:
    return GtmPool.objects.create(device=device, name=name, members=members)


def _gtm_vserver(device: Device, server_name: str, vs_name: str, ip: str, port: str) -> GtmVServer:
    server, _ = GtmServer.objects.get_or_create(device=device, name=server_name)
    return GtmVServer.objects.create(device=device, server=server, name=vs_name, ip_address=ip, port=port)


def _ltm_virtual(
    device: Device, name: str, ip: str, port: str, pool: str = "", rules: list[str] | None = None
) -> LtmVirtualServer:
    return LtmVirtualServer.objects.create(
        device=device, name=name, vs_address=ip, vs_port=port, pool=pool, rules=rules or []
    )


def _build_two_level_chain(hostname: str = "ia-exp") -> Device:
    """GTM VS → LLB → SLB 两级都能命中的链路。

    GTM VS 10.1.1.1:80  →  命中 LLB 虚拟服务器 vs_llb(10.1.1.1:80)
        LLB 池 pool_llb 的成员 10.2.2.2:8080
                            →  命中 SLB 虚拟服务器 vs_slb(10.2.2.2:8080)
                                SLB 池 pool_slb 的成员 10.9.9.9:9090
    """
    gslb = _device(hostname)
    _wideip(gslb, "www.example.com", ["pool_web"])
    _gtm_pool(gslb, "pool_web", [{"server_name": "s1", "vs_name": "vs1"}])
    _gtm_vserver(gslb, "s1", "vs1", "10.1.1.1", "80")

    ltm = _device(f"{hostname}-ltm", "slb")
    _ltm_virtual(ltm, "vs_llb", "10.1.1.1", "80", pool="pool_llb", rules=["irule_llb"])
    LtmPool.objects.create(device=ltm, name="pool_llb", mode="http")
    LtmPoolMember.objects.create(device=ltm, pool_name="pool_llb", name="m_llb", address="10.2.2.2", port="8080")

    _ltm_virtual(ltm, "vs_slb", "10.2.2.2", "8080", pool="pool_slb", rules=["irule_slb"])
    LtmPool.objects.create(device=ltm, name="pool_slb", mode="http")
    LtmPoolMember.objects.create(device=ltm, pool_name="pool_slb", name="m_slb", address="10.9.9.9", port="9090")
    return gslb


# ---------- 列结构 ----------


def test_export_headers_shape():
    """16 列：GTM 四列 + LTM 两级各五列（含 rules）+ 负责人 + 说明"""
    assert len(EXPORT_HEADERS) == 16
    assert EXPORT_HEADERS[0] == "域名"
    assert EXPORT_HEADERS[2:4] == ["GTM 虚拟服务器 IP", "GTM 虚拟服务器端口"]
    assert EXPORT_HEADERS[4:9] == [
        "LLB 虚拟服务器地址",
        "LLB 端口",
        "LLB rules",
        "LLB 后端成员地址",
        "LLB 后端成员端口",
    ]
    assert EXPORT_HEADERS[9:14] == [
        "SLB 虚拟服务器地址",
        "SLB 端口",
        "SLB rules",
        "SLB 后端成员地址",
        "SLB 后端成员端口",
    ]
    assert EXPORT_HEADERS[14] == "负责人"
    assert EXPORT_HEADERS[15] == "说明"
    # 列宽数量必须与表头一致，否则导出会静默少设宽度
    assert len(EXPORT_COLUMN_WIDTHS) == len(EXPORT_HEADERS)


@pytest.mark.django_db
def test_two_level_chain_fills_all_twelve_columns():
    """两级都命中时，GTM 与 LLB / SLB 的列应全部填满"""
    gslb = _build_two_level_chain("ia-two")
    rows = build_path_rows(analyze_device(gslb))

    assert len(rows) == 1
    row = rows[0]
    assert row["wideip"] == "www.example.com"
    assert row["rtype"] == "A"
    # GTM 侧
    assert (row["gtm_ip"], row["gtm_port"]) == ("10.1.1.1", "80")
    # LLB：GTM VS 的 ip:port 命中的那一级
    assert (row["llb_address"], row["llb_port"]) == ("10.1.1.1", "80")
    assert (row["llb_member_address"], row["llb_member_port"]) == ("10.2.2.2", "8080")
    # SLB：LLB 池成员的 address:port 再命中的那一级
    assert (row["slb_address"], row["slb_port"]) == ("10.2.2.2", "8080")
    assert (row["slb_member_address"], row["slb_member_port"]) == ("10.9.9.9", "9090")
    assert row["note"] == ""


@pytest.mark.django_db
def test_single_level_chain_leaves_slb_columns_empty():
    """只有一级 LTM 时 SLB 四列为空，并在说明里标注"""
    gslb = _device("ia-one")
    _wideip(gslb, "one.example.com", ["pool_web"])
    _gtm_pool(gslb, "pool_web", [{"server_name": "s1", "vs_name": "vs1"}])
    _gtm_vserver(gslb, "s1", "vs1", "10.1.1.1", "80")

    ltm = _device("ia-one-ltm", "slb")
    _ltm_virtual(ltm, "vs_llb", "10.1.1.1", "80", pool="pool_llb")
    LtmPool.objects.create(device=ltm, name="pool_llb", mode="http")
    LtmPoolMember.objects.create(device=ltm, pool_name="pool_llb", name="m_llb", address="10.2.2.2", port="8080")

    row = build_path_rows(analyze_device(gslb))[0]

    assert (row["llb_address"], row["llb_port"]) == ("10.1.1.1", "80")
    assert (row["llb_member_address"], row["llb_member_port"]) == ("10.2.2.2", "8080")
    assert (row["slb_address"], row["slb_port"]) == ("", "")
    assert (row["slb_member_address"], row["slb_member_port"]) == ("", "")
    assert row["note"] == "仅一级 LTM"


@pytest.mark.django_db
def test_ltm_not_found_leaves_ltm_columns_empty():
    """GTM 有虚拟服务器但没有对应 LTM 时，LTM 两级的八列全空"""
    gslb = _device("ia-noltm")
    _wideip(gslb, "noltm.example.com", ["pool_web"])
    _gtm_pool(gslb, "pool_web", [{"server_name": "s1", "vs_name": "vs1"}])
    _gtm_vserver(gslb, "s1", "vs1", "10.1.1.1", "80")

    row = build_path_rows(analyze_device(gslb))[0]

    assert (row["gtm_ip"], row["gtm_port"]) == ("10.1.1.1", "80")
    assert row["llb_address"] == ""
    assert row["llb_member_address"] == ""
    assert row["slb_address"] == ""
    assert "无对应 LTM 虚拟服务器" in row["note"]


@pytest.mark.django_db
def test_vserver_not_found_leaves_everything_but_wideip_empty():
    """GTM 虚拟服务器都没找到时，只有域名与类型有值"""
    gslb = _device("ia-novs")
    _wideip(gslb, "novs.example.com", ["pool_web"])
    _gtm_pool(gslb, "pool_web", [{"server_name": "s1", "vs_name": "vs1"}])

    row = build_path_rows(analyze_device(gslb))[0]

    assert row["wideip"] == "novs.example.com"
    assert row["rtype"] == "A"
    assert row["gtm_ip"] == ""
    assert row["llb_address"] == ""
    assert row["note"] == "GTM 虚拟服务器未找到"


@pytest.mark.django_db
def test_members_expand_into_multiple_rows():
    """同一池的多个成员各占一行"""
    gslb = _device("ia-multi")
    _wideip(gslb, "multi.example.com", ["pool_web"])
    _gtm_pool(
        gslb,
        "pool_web",
        [
            {"server_name": "s1", "vs_name": "vs1", "member_order": 0},
            {"server_name": "s2", "vs_name": "vs2", "member_order": 1},
        ],
    )
    _gtm_vserver(gslb, "s1", "vs1", "10.1.1.1", "80")
    _gtm_vserver(gslb, "s2", "vs2", "10.1.1.2", "80")

    rows = build_path_rows(analyze_device(gslb))

    assert [row["gtm_ip"] for row in rows] == ["10.1.1.1", "10.1.1.2"]


@pytest.mark.django_db
def test_empty_pool_still_produces_a_row():
    """池没有成员时也要留一行，否则这条记录会从表里消失"""
    gslb = _device("ia-empty")
    _wideip(gslb, "empty.example.com", ["pool_missing"])

    rows = build_path_rows(analyze_device(gslb))

    assert len(rows) == 1
    assert rows[0]["wideip"] == "empty.example.com"
    assert rows[0]["note"] == "池未找到"


# ---------- xlsx 导出 ----------


@pytest.mark.django_db
def test_export_returns_xlsx_workbook():
    gslb = _build_two_level_chain("ia-xlsx")
    # 链路最后的 IP 是 SLB 池成员 10.9.9.9，按它反查负责人
    ServerOwner.objects.create(hostname="srv-final", ip="10.9.9.9", owner="张三")
    _analyze(gslb)

    res = Client().get(EXPORT_URL, {"device": gslb.pk})

    assert res.status_code == 200
    assert res["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "attachment" in res["Content-Disposition"]
    assert "ia-xlsx" in res["Content-Disposition"]

    wb = load_workbook(BytesIO(res.content))
    sheet = wb.active
    if sheet is None:
        sheet = wb.create_sheet()

    assert sheet.title == "互联网资产分析"
    assert [cell.value for cell in sheet[1]] == EXPORT_HEADERS
    assert sheet.max_row == 2

    # 导出列顺序要与字段一一对应（空说明单元格 openpyxl 写的是 None）
    values = [sheet.cell(row=2, column=index).value for index in range(1, 17)]
    assert values == [
        "www.example.com",
        "A",
        "10.1.1.1",
        "80",
        "10.1.1.1",
        "80",
        "irule_llb",
        "10.2.2.2",
        "8080",
        "10.2.2.2",
        "8080",
        "irule_slb",
        "10.9.9.9",
        "9090",
        "张三",
        None,
    ]


@pytest.mark.django_db
def test_export_requires_device_param():
    assert Client().get(EXPORT_URL).status_code == 400


@pytest.mark.django_db
def test_export_unknown_device_returns_404():
    assert Client().get(EXPORT_URL, {"device": 999999}).status_code == 404


# ---------- rules 列与负责人 ----------


@pytest.mark.django_db
def test_llb_and_slb_rules_columns():
    """两级虚拟服务器各自的 iRules 落在各自那一列"""
    gslb = _build_two_level_chain("ia-rules")
    row = build_path_rows(analyze_device(gslb))[0]

    assert row["llb_rules"] == "irule_llb"
    assert row["slb_rules"] == "irule_slb"


@pytest.mark.django_db
def test_owner_resolved_from_deepest_member_ip():
    """负责人按链路最后的 IP 反查：两级链路取 SLB 池成员地址"""
    gslb = _build_two_level_chain("ia-owner")
    ServerOwner.objects.create(ip="10.9.9.9", owner="最终负责人")
    # 干扰项：中间那一跳的地址也建一条，不能取它
    ServerOwner.objects.create(ip="10.2.2.2", owner="中间负责人")

    row = build_path_rows(analyze_device(gslb))[0]

    assert row["owner"] == "最终负责人"


@pytest.mark.django_db
def test_owner_falls_back_to_llb_member_when_single_level():
    """只有一级 LTM 时，最后的 IP 是 LLB 池成员地址"""
    gslb = _device("ia-owner-one")
    _wideip(gslb, "one.example.com", ["pool_web"])
    _gtm_pool(gslb, "pool_web", [{"server_name": "s1", "vs_name": "vs1"}])
    _gtm_vserver(gslb, "s1", "vs1", "10.1.1.1", "80")

    ltm = _device("ia-owner-one-ltm", "slb")
    _ltm_virtual(ltm, "vs_llb", "10.1.1.1", "80", pool="pool_llb")
    LtmPool.objects.create(device=ltm, name="pool_llb", mode="http")
    LtmPoolMember.objects.create(device=ltm, pool_name="pool_llb", name="m", address="10.5.5.5", port="8080")
    ServerOwner.objects.create(ip="10.5.5.5", owner="一级负责人")

    row = build_path_rows(analyze_device(gslb))[0]

    assert row["slb_member_address"] == ""
    assert row["owner"] == "一级负责人"


@pytest.mark.django_db
def test_owner_falls_back_to_gtm_ip_when_chain_breaks():
    """链路断在「无对应 LTM 虚拟服务器」时，用 GTM 虚拟服务器地址反查"""
    gslb = _device("ia-owner-break")
    _wideip(gslb, "break.example.com", ["pool_web"])
    _gtm_pool(gslb, "pool_web", [{"server_name": "s1", "vs_name": "vs1"}])
    _gtm_vserver(gslb, "s1", "vs1", "10.7.7.7", "80")
    ServerOwner.objects.create(ip="10.7.7.7", owner="断链负责人")

    row = build_path_rows(analyze_device(gslb))[0]

    assert row["note"] == "无对应 LTM 虚拟服务器 · GTM 虚拟服务器地址即最终地址"
    assert row["owner"] == "断链负责人"


@pytest.mark.django_db
def test_disabled_owner_is_ignored():
    """status=disabled 的负责人记录不参与匹配"""
    gslb = _build_two_level_chain("ia-owner-off")
    ServerOwner.objects.create(ip="10.9.9.9", owner="已停用", status="disabled")

    assert build_path_rows(analyze_device(gslb))[0]["owner"] == ""


@pytest.mark.django_db
def test_owner_matches_ipv6_regardless_of_writing():
    """IPv6 写法不同（大小写 / 展开）也要能匹配上负责人"""
    gslb = _device("ia-owner-v6")
    _wideip(gslb, "v6.example.com", ["pool_web"])
    _gtm_pool(gslb, "pool_web", [{"server_name": "s1", "vs_name": "vs1"}])
    _gtm_vserver(gslb, "s1", "vs1", "2001:db8::1", "80")

    ltm = _device("ia-owner-v6-ltm", "slb")
    _ltm_virtual(ltm, "vs_llb", "2001:0DB8:0000::1", "80", pool="pool_llb")
    LtmPool.objects.create(device=ltm, name="pool_llb", mode="http")
    LtmPoolMember.objects.create(device=ltm, pool_name="pool_llb", name="m", address="2001:DB8::99", port="80")
    ServerOwner.objects.create(ip="2001:0db8::99", owner="v6 负责人")

    row = build_path_rows(analyze_device(gslb))[0]

    assert row["llb_member_address"] == "2001:DB8::99"
    assert row["owner"] == "v6 负责人"
