"""xlsx 解析健壮性：样式表损坏不能拖垮单元格值（真实文件踩过）。

构造手法：用 openpyxl 写一个正常文件，再把 styles.xml 里每个 <fill> 的子节点清空
（模拟写出空 <fill/> 的导出器）——openpyxl 的样式解析会
``TypeError: expected <class 'openpyxl.styles.fills.Fill'>``、整个文件判死，
而 ``parse_xlsx`` 必须照常拿到值，且日期格不失真。
"""

import zipfile
from datetime import datetime
from io import BytesIO
from xml.etree import ElementTree

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook, load_workbook
from sheets.xlsx_io import parse_xlsx

SHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _build_xlsx() -> BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "数据"
    ws.append(["名称", "数量", "日期", "开关"])
    ws.append(["甲", 1, datetime(2024, 1, 1), True])
    ws.append(["乙", 2.5, datetime(2024, 6, 30, 8, 30), False])
    ws["C2"].number_format = "yyyy-mm-dd"
    ws["C3"].number_format = "yyyy/m/d h:mm"
    buf = BytesIO()
    wb.save(buf)
    return buf


def _corrupt_styles(xlsx: BytesIO) -> BytesIO:
    """清空每个 <fill> 的子节点 → openpyxl 样式解析必炸，值不受影响。"""
    src = zipfile.ZipFile(xlsx)
    out = BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "xl/styles.xml":
                root = ElementTree.fromstring(data)
                for fill in root.iter(f"{SHEET_NS}fill"):
                    for child in list(fill):
                        fill.remove(child)
                data = ElementTree.tostring(root)
            dst.writestr(item, data)
    src.close()
    out.seek(0)
    return out


EXPECTED_ROWS = [
    ["名称", "数量", "日期", "开关"],
    ["甲", 1, "2024-01-01T00:00:00", True],
    ["乙", 2.5, "2024-06-30T08:30:00", False],
]


def test_parse_normal_xlsx():
    data = parse_xlsx(_build_xlsx())

    assert data == {"sheets": [{"name": "数据", "rows": EXPECTED_ROWS}]}


def test_openpyxl_itself_rejects_corrupted_styles():
    """根因钉住：坏 <fill/> 会让 openpyxl 正常解析整个文件失败（此测试红了 = openpyxl 修了/行为变了）。"""
    with pytest.raises(TypeError, match="openpyxl"):
        load_workbook(_corrupt_styles(_build_xlsx()), read_only=True, data_only=True)


def test_parse_survives_corrupted_styles_and_keeps_values_and_dates():
    data = parse_xlsx(_corrupt_styles(_build_xlsx()))

    # 值全保住；日期格经自扫 numFmt 识别，仍是 ISO 串而不是序列号
    assert data == {"sheets": [{"name": "数据", "rows": EXPECTED_ROWS}]}


def test_parse_survives_styles_without_numfmt_info():
    """坏到 numFmt 都读不出：日期退化成数字也要能出值（不许整体失败）。"""
    xlsx = _corrupt_styles(_build_xlsx())
    src = zipfile.ZipFile(xlsx)
    out = BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "xl/styles.xml":
                data = b'<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fills count="1"><fill/></fills></styleSheet>'
            dst.writestr(item, data)
    src.close()
    out.seek(0)

    rows = parse_xlsx(out)["sheets"][0]["rows"]

    assert rows[0] == EXPECTED_ROWS[0]
    assert rows[1][0] == "甲"
    assert rows[1][1] == 1
    assert rows[1][2] == 45292.0  # 2024-01-01 的 Excel 序列号
    assert rows[1][3] is True


@pytest.mark.django_db
def test_upload_with_corrupted_styles(operator_client):
    f = SimpleUploadedFile("坏样式.xlsx", _corrupt_styles(_build_xlsx()).getvalue())

    resp = operator_client.post("/api/sheets/upload/", {"file": f}, format="multipart")

    assert resp.status_code == 201
    assert resp.json()["data"] == {"sheets": [{"name": "数据", "rows": EXPECTED_ROWS}]}


# ---------------------------------------------------------------------------
# 合并单元格：拆分填充（区域内每格写上左上角的值）
# ---------------------------------------------------------------------------


def _build_merged_xlsx() -> BytesIO:
    wb = Workbook()
    ws0 = wb.active
    ws0.title = "普通"
    ws0.append(["a", "b"])
    ws = wb.create_sheet("合并")
    ws.append(["大标题", None, None])
    ws.append(["甲", 1, None])
    ws.append(["乙", None, "x"])
    ws.merge_cells("A1:C1")  # 横向合并：标题铺满整行
    ws.merge_cells("B2:B3")  # 纵向合并：1 铺满 B2:B3
    buf = BytesIO()
    wb.save(buf)
    return buf


MERGED_ROWS = [
    ["大标题", "大标题", "大标题"],
    ["甲", 1, None],
    ["乙", 1, "x"],
]


def test_parse_unmerges_and_fills_merged_cells():
    data = parse_xlsx(_build_merged_xlsx())

    assert data == {"sheets": [{"name": "普通", "rows": [["a", "b"]]}, {"name": "合并", "rows": MERGED_ROWS}]}


def test_parse_fills_merged_even_with_corrupted_styles():
    """降级路径（样式损坏）也走同一套合并填充——合并信息与样式无关。"""
    data = parse_xlsx(_corrupt_styles(_build_merged_xlsx()))

    assert data["sheets"][1] == {"name": "合并", "rows": MERGED_ROWS}


@pytest.mark.django_db
def test_upload_merged_cells_filled(operator_client):
    f = SimpleUploadedFile("合并.xlsx", _build_merged_xlsx().getvalue())

    resp = operator_client.post("/api/sheets/upload/", {"file": f}, format="multipart")

    assert resp.status_code == 201
    assert resp.json()["data"]["sheets"][1]["rows"] == MERGED_ROWS
