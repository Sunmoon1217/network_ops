"""xlsx ↔ data 结构的互转（openpyxl 只在本模块出现）。

data 结构见 ``sheets.models.Spreadsheet`` 的文档串；本模块负责两件事：

- ``parse_xlsx``：上传的 xlsx → data（每张表的第 1 行即表头行，尾部空行/空列裁掉）；
- ``build_xlsx``：data → xlsx 字节串（导出当前版本或历史版本共用）。
"""

from datetime import date, datetime, time
from io import BytesIO

from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter

# 单元格字符数上限（Excel 自身的上限），导出超限 openpyxl 会直接抛错，提前在这里兜住
MAX_CELL_STR_LEN = 32767
# 列宽估算上限：中文按两个字符宽估，超长内容截断展示宽度，不把整张表撑爆
MAX_COL_WIDTH = 60


def _cell(value):
    """openpyxl 单元格值 → JSON 标量。"""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if value == value and value not in (float("inf"), float("-inf")) else str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return str(value)


def _trim(rows):
    """裁掉尾部全空行与尾部全空列（Excel 的 used range 常带大片空白）。"""
    while rows and all(v is None or v == "" for v in rows[-1]):
        rows.pop()
    width = 0
    for row in rows:
        for idx, v in enumerate(row, start=1):
            if v is not None and v != "":
                width = max(width, idx)
    return [row[:width] for row in rows]


def parse_xlsx(file) -> dict:
    """把上传的 xlsx 文件对象解析成 data 结构。"""
    wb = load_workbook(file, read_only=True, data_only=True)
    try:
        sheets = []
        for ws in wb.worksheets:
            rows = _trim([[_cell(v) for v in row] for row in ws.iter_rows(values_only=True)])
            sheets.append({"name": ws.title, "rows": rows})
        return {"sheets": sheets}
    finally:
        wb.close()


def build_xlsx(data: dict) -> bytes:
    """把 data 结构生成 xlsx 字节串。"""
    wb = Workbook()
    wb.remove(wb.active)
    for sheet in data.get("sheets", []):
        ws = wb.create_sheet(title=str(sheet.get("name", ""))[:31] or "Sheet")
        width = 0
        for row in sheet.get("rows", []):
            ws.append(["" if v is None else v for v in row])
            width = max(width, len(row))
        for idx in range(1, width + 1):
            column = get_column_letter(idx)
            longest = max((len(str(row[idx - 1])) for row in sheet.get("rows", []) if idx <= len(row)), default=4)
            ws.column_dimensions[column].width = min(longest * 2 + 4, MAX_COL_WIDTH)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
