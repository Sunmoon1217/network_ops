"""Excel 导入：新增「设备组」Sheet 与模板下载接口。

覆盖：
- `_import_device_groups` 建组 + 建成员，中文显示名与 key 都认，空值走默认
- 设备不存在 / 组类型 / 角色非法的行逐行报错，且**不建半截数据**
- 模板接口的 Sheet 与列头取自 `IMPORT_SHEETS`，与 `import_excel` 分发的是同一份表
  （改列头只改一处，模板与导入不可能漂移）
"""

from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook, load_workbook
from rest_framework.test import APIClient

from assets.api.views import IMPORT_SHEETS, _import_device_groups
from assets.models import Device, DeviceGroup, DeviceGroupMember

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _device(hostname: str) -> Device:
    return Device.objects.create(hostname=hostname, device_type="switch")


def _sheet(rows, headers=None):
    ws = Workbook().active
    ws.title = "设备组"  # 直接调 importer 无所谓，走 HTTP 分发时 Sheet 名就是 key
    ws.append(headers or IMPORT_SHEETS["设备组"]["headers"])
    for row in rows:
        ws.append(row)
    return ws


@pytest.mark.django_db
def test_import_creates_group_and_members():
    """中文显示名（堆叠/主/备）归一成模型 key，同组多行 = 多个成员"""
    _device("imp-grp-m")
    _device("imp-grp-b")

    result = _import_device_groups(
        _sheet(
            [
                ["imp-stack", "堆叠", "接入交换机堆叠", "imp-grp-m", "主"],
                ["imp-stack", "堆叠", "接入交换机堆叠", "imp-grp-b", "备"],
            ]
        )
    )

    assert result["created"] == 2 and not result["errors"], result
    group = DeviceGroup.objects.get(name="imp-stack")
    assert group.group_type == "stack"
    assert group.description == "接入交换机堆叠"
    assert set(group.members.values_list("device__hostname", "device_role")) == {
        ("imp-grp-m", "master"),
        ("imp-grp-b", "backup"),
    }


@pytest.mark.django_db
def test_import_defaults_empty_type_and_role():
    """组类型 / 角色留空 → single / member（与模型默认一致）"""
    device = _device("imp-grp-default")

    result = _import_device_groups(_sheet([["imp-single", "", "", "imp-grp-default", ""]]))

    assert result["created"] == 1 and not result["errors"], result
    group = DeviceGroup.objects.get(name="imp-single")
    assert group.group_type == "single"
    member = group.members.get()
    assert member.device == device
    assert member.device_role == "member"


@pytest.mark.django_db
def test_import_reports_bad_rows_without_partial_group():
    """未知设备 / 组类型 / 角色逐行报错；报错行不许留下半截组"""
    _device("imp-grp-ok")

    result = _import_device_groups(
        _sheet(
            [
                ["imp-bad-dev", "ha", "", "imp-not-exist", "主"],
                ["imp-bad-type", "机架", "", "imp-grp-ok", "主"],
                ["imp-bad-role", "ha", "", "imp-grp-ok", "老大"],
            ]
        )
    )

    assert result["created"] == 0
    assert len(result["errors"]) == 3, result
    assert any("设备 'imp-not-exist' 不存在" in e for e in result["errors"])
    assert any("未知组类型" in e for e in result["errors"])
    assert any("未知角色" in e for e in result["errors"])
    assert not DeviceGroup.objects.filter(name__in=["imp-bad-dev", "imp-bad-type", "imp-bad-role"]).exists(), (
        "报错行不该建出组"
    )


@pytest.mark.django_db
def test_reimport_updates_member_role():
    """重复导入同一行按「更新」计数，且角色被新值覆盖"""
    device = _device("imp-grp-re")
    rows = [["imp-ha", "主备", "", "imp-grp-re", "备"]]

    first = _import_device_groups(_sheet(rows))
    second = _import_device_groups(_sheet([["imp-ha", "主备", "", "imp-grp-re", "主"]]))

    assert first["created"] == 1 and first["updated"] == 0, first
    assert second["created"] == 0 and second["updated"] == 1, second
    assert DeviceGroup.objects.filter(name="imp-ha").count() == 1
    member = DeviceGroupMember.objects.get(group__name="imp-ha", device=device)
    assert member.device_role == "master"


def test_template_lists_every_import_sheet():
    """模板的 Sheet 与列头 == IMPORT_SHEETS（同一份表），设备组 Sheet 必须在"""
    resp = APIClient().get("/api/assets/import-template/")

    assert resp.status_code == 200
    assert "spreadsheetml" in resp["Content-Type"]

    wb = load_workbook(BytesIO(resp.content))
    assert wb.sheetnames == list(IMPORT_SHEETS), "模板 Sheet 清单/顺序要与导入分发一致"
    assert "设备组" in wb.sheetnames

    for sheet_name, spec in IMPORT_SHEETS.items():
        header_row = [cell.value for cell in wb[sheet_name][1]]
        assert header_row == spec["headers"], f"{sheet_name} 列头与导入实现不一致"
    assert wb["设备组"][1][0].value == "组名"


@pytest.mark.django_db
def test_import_excel_dispatches_device_group_sheet():
    """走完整 HTTP 导入链：设备组 Sheet 被 IMPORT_SHEETS 认出并分发"""
    _device("imp-http-dev")

    buf = BytesIO()
    _sheet([["imp-http-grp", "cluster", "集群组", "imp-http-dev", ""]]).parent.save(buf)
    upload = SimpleUploadedFile("import.xlsx", buf.getvalue(), XLSX_CONTENT_TYPE)

    payload = APIClient().post("/api/assets/import-devices/", {"file": upload}).json()

    assert payload["success"] is True
    assert payload["results"]["设备组"]["created"] == 1, payload
    assert payload["results"]["配置文件"]["skipped"] is True, "未提供的 Sheet 应记为跳过"
    assert DeviceGroup.objects.filter(name="imp-http-grp", group_type="cluster").exists()
