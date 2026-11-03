"""`/api/docs/spreadsheets/`：通用表格（上传 / 保存 / 修改历史 / 回滚 / 导出）。

守住的边界：

- 上传 xlsx → 解析成 data、落 v1 初始版本；解析失败 / 非 xlsx 400；
- 保存即落**全量快照 + 单元格级 diff** 的新版本；**无改动不建版本**（历史不刷屏）；
- 修改历史按版本列出，单版本能拿到快照与变更明细；
- 回滚是「以一次新保存落地」，历史不被改写；
- 导出默认当前版本、`?revision=N` 导出历史版本；
- 权限走全局 IsOperatorOrReadOnly：普通用户只读，上传/保存/恢复/删除都要操作员。
"""

from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook, load_workbook
from rest_framework.test import APIClient

from docs.models import Spreadsheet, SpreadsheetRevision

LIST_URL = "/api/docs/spreadsheets/"
UPLOAD_URL = "/api/docs/spreadsheets/upload/"


def _xlsx_bytes(sheets: dict) -> bytes:
    """{sheet_name: rows} → xlsx 字节串。"""
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(title=name)
        for row in rows:
            ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _upload(client, sheets=None, filename="测试表.xlsx"):
    sheets = sheets if sheets is not None else {"Sheet1": [["列1", "列2"], ["a", 1]], "附表": [["x"]]}
    f = SimpleUploadedFile(filename, _xlsx_bytes(sheets))
    return client.post(UPLOAD_URL, {"file": f}, format="multipart")


@pytest.mark.django_db
def test_upload_creates_spreadsheet_and_first_revision(operator_client):
    resp = _upload(operator_client)

    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "测试表"
    assert body["latest_revision"] == 1
    assert body["sheet_names"] == ["Sheet1", "附表"]
    assert body["data"] == {"sheets": [{"name": "Sheet1", "rows": [["列1", "列2"], ["a", 1]]}, {"name": "附表", "rows": [["x"]]}]}
    assert body["created_by"] == "_t_operator"

    rev = SpreadsheetRevision.objects.get(spreadsheet_id=body["id"], revision=1)
    assert rev.note == "初始导入"
    assert rev.changes == []


@pytest.mark.django_db
def test_upload_rejects_bad_file(operator_client):
    resp = operator_client.post(UPLOAD_URL, {"file": SimpleUploadedFile("x.txt", b"not xlsx")}, format="multipart")
    assert resp.status_code == 400

    resp = operator_client.post(UPLOAD_URL, {"file": SimpleUploadedFile("x.xlsx", b"broken")}, format="multipart")
    assert resp.status_code == 400
    assert "解析失败" in resp.json()["detail"]

    resp = operator_client.post(UPLOAD_URL, {}, format="multipart")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_save_records_cell_diff_and_history(operator_client):
    sp_id = _upload(operator_client).json()["id"]
    detail = operator_client.get(f"/api/docs/spreadsheets/{sp_id}/").json()

    # 改一个单元格 + 加一行
    detail["data"]["sheets"][0]["rows"][1][0] = "改过的值"
    detail["data"]["sheets"][0]["rows"].append(["新增", "行"])
    resp = operator_client.put(f"/api/docs/spreadsheets/{sp_id}/", {"data": detail["data"], "note": "补一行"}, format="json")

    assert resp.status_code == 201
    save = resp.json()
    assert save["created"] is True
    assert save["revision"] == 2
    assert save["summary"]["cells_changed"] == 1
    assert save["summary"]["rows_added"] == 1
    assert {"sheet": "Sheet1", "row": 1, "col": 0, "old": "a", "new": "改过的值"} in save["changes"]

    history = operator_client.get(f"/api/docs/spreadsheets/{sp_id}/revisions/").json()["results"]
    assert [r["revision"] for r in history] == [2, 1]
    assert history[0]["note"] == "补一行"
    assert history[0]["created_by"] == "_t_operator"

    rev2 = operator_client.get(f"/api/docs/spreadsheets/{sp_id}/revisions/2/").json()
    assert rev2["data"]["sheets"][0]["rows"][1][0] == "改过的值"
    assert rev2["summary"]["cells_changed"] == 1


@pytest.mark.django_db
def test_save_without_changes_creates_no_revision(operator_client):
    sp_id = _upload(operator_client).json()["id"]
    data = operator_client.get(f"/api/docs/spreadsheets/{sp_id}/").json()["data"]

    resp = operator_client.put(f"/api/docs/spreadsheets/{sp_id}/", {"data": data}, format="json")

    assert resp.status_code == 200
    assert resp.json()["created"] is False
    assert SpreadsheetRevision.objects.filter(spreadsheet_id=sp_id).count() == 1


@pytest.mark.django_db
def test_save_rejects_invalid_data(operator_client):
    sp_id = _upload(operator_client).json()["id"]

    resp = operator_client.put(f"/api/docs/spreadsheets/{sp_id}/", {"data": {"sheets": []}}, format="json")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_restore_creates_new_revision_without_rewriting_history(operator_client):
    sp_id = _upload(operator_client).json()["id"]
    data = operator_client.get(f"/api/docs/spreadsheets/{sp_id}/").json()["data"]
    data["sheets"][0]["rows"][1][0] = "v2 改动"
    operator_client.put(f"/api/docs/spreadsheets/{sp_id}/", {"data": data}, format="json")

    resp = operator_client.post(f"/api/docs/spreadsheets/{sp_id}/revisions/1/restore/")

    assert resp.status_code == 201
    save = resp.json()
    assert save["created"] is True
    assert save["revision"] == 3
    # 回滚 = 相对 v2 反向改回来
    assert save["summary"]["cells_changed"] == 1

    current = operator_client.get(f"/api/docs/spreadsheets/{sp_id}/").json()
    assert current["latest_revision"] == 3
    assert current["data"]["sheets"][0]["rows"][1][0] == "a"
    # 历史仍是 3 个版本，v2 的快照原样保留
    assert SpreadsheetRevision.objects.filter(spreadsheet_id=sp_id).count() == 3
    assert operator_client.get(f"/api/docs/spreadsheets/{sp_id}/revisions/2/").json()["data"]["sheets"][0]["rows"][1][0] == "v2 改动"


@pytest.mark.django_db
def test_export_current_and_historical_revision(operator_client):
    sp_id = _upload(operator_client).json()["id"]
    data = operator_client.get(f"/api/docs/spreadsheets/{sp_id}/").json()["data"]
    data["sheets"][0]["rows"][1][0] = "新值"
    operator_client.put(f"/api/docs/spreadsheets/{sp_id}/", {"data": data}, format="json")

    resp = operator_client.get(f"/api/docs/spreadsheets/{sp_id}/export/")
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    wb = load_workbook(BytesIO(resp.content), read_only=True)
    assert list(wb.sheetnames) == ["Sheet1", "附表"]
    rows = list(wb["Sheet1"].iter_rows(values_only=True))
    assert rows[1][0] == "新值"

    resp = operator_client.get(f"/api/docs/spreadsheets/{sp_id}/export/?revision=1")
    wb = load_workbook(BytesIO(resp.content), read_only=True)
    assert list(wb["Sheet1"].iter_rows(values_only=True))[1][0] == "a"

    assert operator_client.get(f"/api/docs/spreadsheets/{sp_id}/export/?revision=abc").status_code == 400


@pytest.mark.django_db
def test_delete(operator_client):
    sp_id = _upload(operator_client).json()["id"]

    assert operator_client.delete(f"/api/docs/spreadsheets/{sp_id}/").status_code == 204
    assert not Spreadsheet.objects.filter(pk=sp_id).exists()
    # 级联删历史
    assert not SpreadsheetRevision.objects.filter(spreadsheet_id=sp_id).exists()


@pytest.mark.django_db
def test_normal_user_is_read_only(normal_user, operator_client):
    sp_id = _upload(operator_client).json()["id"]
    client = APIClient()
    client.force_authenticate(user=normal_user)

    assert client.get(LIST_URL).status_code == 200
    assert client.get(f"/api/docs/spreadsheets/{sp_id}/").status_code == 200
    assert client.get(f"/api/docs/spreadsheets/{sp_id}/export/").status_code == 200

    data = client.get(f"/api/docs/spreadsheets/{sp_id}/").json()["data"]
    assert client.put(f"/api/docs/spreadsheets/{sp_id}/", {"data": data}, format="json").status_code == 403
    assert client.post(f"/api/docs/spreadsheets/{sp_id}/revisions/1/restore/").status_code == 403
    assert client.delete(f"/api/docs/spreadsheets/{sp_id}/").status_code == 403
    assert client.post(UPLOAD_URL, {"file": SimpleUploadedFile("a.xlsx", _xlsx_bytes({"S": [["h"]]}))}, format="multipart").status_code == 403


@pytest.mark.django_db
def test_unauthenticated_rejected():
    assert APIClient().get(LIST_URL).status_code == 401


@pytest.mark.django_db
def test_save_header_rows_change_creates_revision(operator_client):
    """只改表头行数也要落版本（格子没动），原样再保存不建版本。"""
    sp_id = _upload(operator_client).json()["id"]
    data = operator_client.get(f"/api/docs/spreadsheets/{sp_id}/").json()["data"]

    data["sheets"][0]["header_rows"] = 2
    resp = operator_client.put(f"/api/docs/spreadsheets/{sp_id}/", {"data": data, "note": "两行表头"}, format="json")

    assert resp.status_code == 201
    save = resp.json()
    assert save["created"] is True
    assert save["summary"]["header_rows_changed"] == 1
    assert save["summary"]["cells_changed"] == 0

    # 原样再保存：无改动、不建版本
    resp = operator_client.put(f"/api/docs/spreadsheets/{sp_id}/", {"data": data}, format="json")
    assert resp.json()["created"] is False
    assert SpreadsheetRevision.objects.filter(spreadsheet_id=sp_id).count() == 2
