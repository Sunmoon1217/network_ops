"""xlsx ↔ data 结构的互转（openpyxl 只在本模块出现）。

data 结构见 ``sheets.models.Spreadsheet`` 的文档串；本模块负责两件事：

- ``parse_xlsx``：上传的 xlsx → data（每张表的第 1 行即表头行，尾部空行/空列裁掉）；
- ``build_xlsx``：data → xlsx 字节串（导出当前版本或历史版本共用）。

``parse_xlsx`` 是**两层解析**：先正常走 openpyxl；失败则降级为「跳过样式表」重试——
样式与单元格值无关，不能让样式拖垮上传。真实文件踩过：有导出器写出缺
patternFill/gradientFill 的空 ``<fill/>``，openpyxl 的 apply_stylesheet 直接
``TypeError: expected <class 'openpyxl.styles.fills.Fill'>``，整个文件判死。
降级路径自扫 numFmt 保住日期识别（日期格不会退化成序列号），其余样式全部放弃。
"""

from datetime import date, datetime, time
from io import BytesIO
from xml.etree import ElementTree

from openpyxl import Workbook, load_workbook
from openpyxl.reader import excel as openpyxl_excel
from openpyxl.styles.numbers import BUILTIN_FORMATS, is_date_format, is_timedelta_format
from openpyxl.utils import get_column_letter

# 单元格字符数上限（Excel 自身的上限），导出超限 openpyxl 会直接抛错，提前在这里兜住
MAX_CELL_STR_LEN = 32767
# 列宽估算上限：中文按两个字符宽估，超长内容截断展示宽度，不把整张表撑爆
MAX_COL_WIDTH = 60

SHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
STYLES_PATH = "xl/styles.xml"


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


def _extract_rows(wb) -> dict:
    try:
        sheets = []
        for ws in wb.worksheets:
            rows = _trim([[_cell(v) for v in row] for row in ws.iter_rows(values_only=True)])
            sheets.append({"name": ws.title, "rows": rows})
        return {"sheets": sheets}
    finally:
        wb.close()


def _lenient_date_formats(styles_bytes: bytes) -> tuple[dict, dict]:
    """自扫样式表的 numFmt → （日期样式表、时间差样式表），键是 cellXfs 里的样式索引。

    只读最简单的 numFmtId/formatCode 属性、全程吞异常——样式表其余部分怎么坏都行，
    坏到 numFmt 都读不出来就返回空（日期退化成数字，但值不丢）。
    """
    date_formats: dict = {}
    timedelta_formats: dict = {}
    try:
        root = ElementTree.fromstring(styles_bytes)
        custom = {}
        for num_fmt in root.iter(f"{SHEET_NS}numFmt"):
            try:
                custom[int(num_fmt.get("numFmtId"))] = num_fmt.get("formatCode", "")
            except (TypeError, ValueError):
                continue
        cell_xfs = root.find(f"{SHEET_NS}cellXfs")
        for style_id, xf in enumerate(list(cell_xfs) if cell_xfs is not None else []):
            try:
                fmt_id = int(xf.get("numFmtId", 0))
            except (TypeError, ValueError):
                continue
            code = custom.get(fmt_id) or BUILTIN_FORMATS.get(fmt_id, "")
            if is_timedelta_format(code):
                timedelta_formats[style_id] = fmt_id
            elif is_date_format(code):
                date_formats[style_id] = fmt_id
    except Exception:
        pass
    return date_formats, timedelta_formats


def _load_values(file, lenient_styles: bool) -> dict:
    """openpyxl 解析单元格值；``lenient_styles`` 时跳过样式表解析（日期识别自扫兜底）。"""
    if not lenient_styles:
        file.seek(0)
        return _extract_rows(load_workbook(file, read_only=True, data_only=True))

    real_apply = openpyxl_excel.apply_stylesheet

    def apply_stylesheet_lenient(archive, wb):
        try:
            real_apply(archive, wb)
            return
        except Exception:
            pass
        # 样式表损坏：样式全部放弃（读值路径不用它们），只自扫 numFmt 保住日期识别
        try:
            styles_bytes = archive.read(STYLES_PATH)
        except Exception:
            styles_bytes = b""
        wb._fonts, wb._fills, wb._borders = [], [], []
        wb._cell_styles, wb._differential_styles = [], []
        wb._date_formats, wb._timedelta_formats = _lenient_date_formats(styles_bytes)

    # 短暂替换 openpyxl 的样式入口、用完即还原（并发上传的最坏情况只是另一请求拿到
    # 同款宽松样式解析，值不受影响）
    openpyxl_excel.apply_stylesheet = apply_stylesheet_lenient
    try:
        file.seek(0)
        return _extract_rows(load_workbook(file, read_only=True, data_only=True))
    finally:
        openpyxl_excel.apply_stylesheet = real_apply


def parse_xlsx(file) -> dict:
    """把上传的 xlsx 文件对象解析成 data 结构（样式表损坏自动降级）。"""
    try:
        return _load_values(file, lenient_styles=False)
    except Exception:
        return _load_values(file, lenient_styles=True)


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
