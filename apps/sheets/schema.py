"""data 载荷的校验与归一（保存接口的入参闸门）。

规则全部面向「通用表格」：结构是矩形网格、单元格是 JSON 标量，
只挡会破坏导出或拖垮存储的东西（非法 sheet 名、超大网格、NaN/Inf 等），
不猜业务语义。
"""

import math

# 规模上限（通用页面也要有闸门，防止一次误操作把整库写爆）
MAX_SHEETS = 64
MAX_ROWS_PER_SHEET = 20000
MAX_COLS = 512
MAX_TOTAL_CELLS = 200000
MAX_SHEET_NAME_LEN = 31  # Excel 自身的 sheet 名长度上限
MAX_CELL_STR_LEN = 32767  # Excel 单元格字符上限
# Excel 不允许出现在 sheet 名里的字符
INVALID_SHEET_NAME_CHARS = set("[]:*?/\\")


class DataError(ValueError):
    """载荷不合规；消息面向最终用户，直接进 400 响应。"""


def _norm_cell(cell, where: str):
    if cell is None or isinstance(cell, (bool, int, str)):
        if isinstance(cell, str) and len(cell) > MAX_CELL_STR_LEN:
            raise DataError(f"{where}：单元格文本超过 {MAX_CELL_STR_LEN} 个字符")
        return cell
    if isinstance(cell, float):
        if not math.isfinite(cell):
            raise DataError(f"{where}：单元格不能是 NaN/Infinity")
        return cell
    raise DataError(f"{where}：单元格只能是文本/数字/布尔/空")


def normalize_data(payload) -> dict:
    """校验并归一 data 载荷；不合规抛 :class:`DataError`。"""
    if not isinstance(payload, dict):
        raise DataError("数据格式错误：缺少 data 对象")
    sheets = payload.get("sheets")
    if not isinstance(sheets, list) or not sheets:
        raise DataError("数据格式错误：sheets 必须是非空数组")
    if len(sheets) > MAX_SHEETS:
        raise DataError(f"工作表数量超过上限 {MAX_SHEETS}")

    out_sheets = []
    seen_names = set()
    total_cells = 0
    for si, sheet in enumerate(sheets, start=1):
        if not isinstance(sheet, dict):
            raise DataError(f"第 {si} 张表：格式错误")
        name = sheet.get("name")
        if not isinstance(name, str) or not name.strip():
            raise DataError(f"第 {si} 张表：名称不能为空")
        name = name.strip()
        if len(name) > MAX_SHEET_NAME_LEN:
            raise DataError(f"表「{name}」：名称超过 {MAX_SHEET_NAME_LEN} 个字符")
        bad = INVALID_SHEET_NAME_CHARS & set(name)
        if bad:
            raise DataError(f"表「{name}」：名称不能包含 {''.join(sorted(bad))}")
        if name in seen_names:
            raise DataError(f"表「{name}」：名称重复")
        seen_names.add(name)

        rows = sheet.get("rows")
        if not isinstance(rows, list):
            raise DataError(f"表「{name}」：rows 必须是数组")
        if len(rows) > MAX_ROWS_PER_SHEET:
            raise DataError(f"表「{name}」：行数超过上限 {MAX_ROWS_PER_SHEET}")

        out_rows = []
        for ri, row in enumerate(rows, start=1):
            if not isinstance(row, list):
                raise DataError(f"表「{name}」第 {ri} 行：每行必须是数组")
            if len(row) > MAX_COLS:
                raise DataError(f"表「{name}」第 {ri} 行：列数超过上限 {MAX_COLS}")
            total_cells += len(row)
            if total_cells > MAX_TOTAL_CELLS:
                raise DataError(f"表格总单元格数超过上限 {MAX_TOTAL_CELLS}")
            out_rows.append([_norm_cell(c, f"表「{name}」第 {ri} 行") for c in row])
        out_sheets.append({"name": name, "rows": out_rows})
    return {"sheets": out_sheets}
