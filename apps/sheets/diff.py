"""两份 data 之间的差异对比（修改历史的「变更明细 / 变更计数」由此产出）。

对齐口径：sheet 按 **名字** 对齐，行/列按 **索引** 对齐——保存接口收的是整份网格快照，
编辑器对单元格的增删改都会体现在行列索引上，索引 diff 足够表达且不需要额外主键。
表头行数（``header_rows``，缺省 1）单列计数：只改表头行数不动格子也算一次修改。
"""

# 变更明细最多记这么多条（超出只累计计数，summary.truncated 置 True）
MAX_CHANGES = 500

# 计数全为 0 时视为「无改动」，保存接口据此跳过建版本，避免空版本刷屏历史
ZERO_SUMMARY = {
    "cells_changed": 0,
    "rows_added": 0,
    "rows_removed": 0,
    "sheets_added": 0,
    "sheets_removed": 0,
    "header_rows_changed": 0,
}


def _sheet_map(data: dict) -> dict:
    return {str(s.get("name", "")): s for s in (data.get("sheets") or [])}


def _same(a, b) -> bool:
    """值比较：类型不同（1 vs True、1 vs "1"）也算变化。"""
    return a is b or (type(a) is type(b) and a == b)


def diff_data(old: dict, new: dict) -> tuple[list, dict]:
    """对比两份 data，返回 ``(changes, summary)``。

    - ``changes``：``[{sheet, row, col, old, new}]``，超过 ``MAX_CHANGES`` 截断；
    - ``summary``：``{cells_changed, rows_added, rows_removed, sheets_added,
      sheets_removed, header_rows_changed, truncated}``。
    """
    old_map, new_map = _sheet_map(old), _sheet_map(new)
    summary = dict(ZERO_SUMMARY, truncated=False)
    summary["sheets_added"] = len(set(new_map) - set(old_map))
    summary["sheets_removed"] = len(set(old_map) - set(new_map))
    changes: list = []
    for name, new_sheet in new_map.items():
        if name not in old_map:
            continue
        old_sheet = old_map[name]
        if old_sheet.get("header_rows", 1) != new_sheet.get("header_rows", 1):
            summary["header_rows_changed"] += 1
        old_rows = old_sheet.get("rows", []) or []
        new_rows = new_sheet.get("rows", []) or []
        for i in range(max(len(old_rows), len(new_rows))):
            if i >= len(old_rows):
                summary["rows_added"] += 1
                continue
            if i >= len(new_rows):
                summary["rows_removed"] += 1
                continue
            old_row, new_row = old_rows[i], new_rows[i]
            for j in range(max(len(old_row), len(new_row))):
                old_v = old_row[j] if j < len(old_row) else None
                new_v = new_row[j] if j < len(new_row) else None
                if _same(old_v, new_v):
                    continue
                summary["cells_changed"] += 1
                if len(changes) < MAX_CHANGES:
                    changes.append({"sheet": name, "row": i, "col": j, "old": old_v, "new": new_v})
                else:
                    summary["truncated"] = True
    return changes, summary


def is_empty(summary: dict) -> bool:
    """summary 是否表示「什么都没改」。"""
    return all(summary.get(key, 0) == 0 for key in ZERO_SUMMARY)
