"""docs.diff / docs.schema 的纯逻辑测试（不碰数据库）。"""

import pytest

from docs.diff import MAX_CHANGES, diff_data, is_empty
from docs.schema import DataError, normalize_data

# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------


def _data(*sheets):
    return {"sheets": [{"name": name, "rows": rows} for name, rows in sheets]}


def test_diff_cell_change_and_unchanged():
    old = _data(("S1", [["a", "b"], ["c", "d"]]))
    new = _data(("S1", [["a", "b"], ["c", "X"]]))

    changes, summary = diff_data(old, new)

    assert changes == [{"sheet": "S1", "row": 1, "col": 1, "old": "d", "new": "X"}]
    assert summary["cells_changed"] == 1
    assert not is_empty(summary)


def test_diff_row_added_removed():
    old = _data(("S1", [["h"], ["1"], ["2"]]))
    new = _data(("S1", [["h"], ["1"], ["2"], ["3"]]))

    _, summary = diff_data(old, new)
    assert summary["rows_added"] == 1

    # 反向即删除
    _, summary = diff_data(new, old)
    assert summary["rows_removed"] == 1


def test_diff_sheet_added_removed():
    old = _data(("S1", [["h"]]))
    new = _data(("S1", [["h"]]), ("S2", [["h"]]))

    _, summary = diff_data(old, new)
    assert summary["sheets_added"] == 1
    assert not is_empty(summary)

    _, summary = diff_data(new, old)
    assert summary["sheets_removed"] == 1


def test_diff_type_sensitive_values():
    # 1 == True 在 Python 里相等，但类型不同要算变化（Excel 里数字与布尔不是一回事）
    old = _data(("S1", [[1]]))
    new = _data(("S1", [[True]]))

    changes, summary = diff_data(old, new)
    assert summary["cells_changed"] == 1
    assert changes[0]["old"] == 1
    assert changes[0]["new"] is True


def test_diff_truncates_changes_but_counts_all():
    old = _data(("S1", [[None] * 30 for _ in range(40)]))
    new = _data(("S1", [["x"] * 30 for _ in range(40)]))

    changes, summary = diff_data(old, new)

    assert len(changes) == MAX_CHANGES
    assert summary["cells_changed"] == 1200
    assert summary["truncated"] is True


def test_diff_identical_is_empty():
    data = _data(("S1", [["a"], ["b"]]))

    changes, summary = diff_data(data, data)

    assert changes == []
    assert is_empty(summary)


def test_diff_header_rows_change():
    old = _data(("S1", [["a"], ["b"]]))  # 单行表头（不落键）
    new = {"sheets": [{"name": "S1", "header_rows": 2, "rows": [["a"], ["b"]]}]}

    changes, summary = diff_data(old, new)

    # 只改表头行数、格子没动：进摘要、不进明细，且不算「无改动」
    assert changes == []
    assert summary["header_rows_changed"] == 1
    assert summary["cells_changed"] == 0
    assert not is_empty(summary)

    # 显式 header_rows=1 与不落键等价（同样算表头行数变了）
    _, summary = diff_data(new, {"sheets": [{"name": "S1", "header_rows": 1, "rows": [["a"], ["b"]]}]})
    assert summary["header_rows_changed"] == 1


# ---------------------------------------------------------------------------
# schema
# ---------------------------------------------------------------------------


def test_normalize_ok_and_cell_coercion():
    out = normalize_data({"sheets": [{"name": " S1 ", "rows": [["a", 1, True, None, 1.5]]}]})

    assert out == {"sheets": [{"name": "S1", "rows": [["a", 1, True, None, 1.5]]}]}
    # 单行表头不落键
    assert "header_rows" not in out["sheets"][0]


def test_normalize_header_rows():
    out = normalize_data({"sheets": [{"name": "S", "header_rows": 3, "rows": [["a"], ["b"], ["c"]]}]})

    assert out["sheets"][0]["header_rows"] == 3


@pytest.mark.parametrize("bad", [0, 11, "2", True, 2.5, None])
def test_normalize_header_rows_rejects(bad):
    with pytest.raises(DataError, match="表头行数|header_rows"):
        normalize_data({"sheets": [{"name": "S", "header_rows": bad, "rows": [["a"]]}]})


@pytest.mark.parametrize(
    "payload,keyword",
    [
        (None, "data"),
        ({"sheets": []}, "sheets"),
        ({"sheets": [{"name": "a/b", "rows": []}]}, "a/b"),
        ({"sheets": [{"name": "重名", "rows": []}, {"name": "重名", "rows": []}]}, "重名"),
        ({"sheets": [{"name": "S", "rows": [["x"] * 513]}]}, "列数"),
        ({"sheets": [{"name": "S", "rows": [["x" * 40000]]}]}, "字符"),
        ({"sheets": [{"name": "S", "rows": [[float("nan")]]}]}, "NaN"),
        ({"sheets": [{"name": "S", "rows": [[{"nested": 1}]]}]}, "只能是文本"),
    ],
)
def test_normalize_rejects(payload, keyword):
    with pytest.raises(DataError) as exc:
        normalize_data(payload)
    assert keyword in str(exc.value)
