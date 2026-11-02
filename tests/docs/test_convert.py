"""docs.convert 的纯逻辑测试（不碰数据库、不发网络）。"""

import base64
import io

import openpyxl
import pytest
from docx import Document as DocxDocument

from docs.convert import ConvertError, convert

# 1x1 透明 PNG（python-docx 能识别尺寸的最小合法图片）
PNG_1X1 = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def _docx_bytes(paragraphs, image: bytes | None = None) -> bytes:
    """按 (文本, 样式名) 列表造 docx，可选插一张内嵌图片。"""
    d = DocxDocument()
    for text, style in paragraphs:
        d.add_paragraph(text, style=style)
    if image is not None:
        d.add_picture(io.BytesIO(image))
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _xlsx_bytes(sheets: dict) -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# txt / csv / xlsx / pdf
# ---------------------------------------------------------------------------


def test_txt_utf8_to_md():
    out = convert("说明.txt", "第一行\n第二行".encode("utf-8"))
    assert (out.target_format, out.text, out.has_images) == ("md", "第一行\n第二行", False)


def test_txt_gb18030_decoded():
    out = convert("老文件.txt", "设备台账".encode("gb18030"))
    assert out.text == "设备台账"


def test_txt_undecodable_rejected():
    with pytest.raises(ConvertError, match="解码失败"):
        convert("坏.txt", b"\xff\xfe\xff\xfa\xff")


def test_csv_to_md_table():
    out = convert("表.csv", "名称,IP\nFW01,10.0.0.1\n".encode("utf-8"))
    assert out.target_format == "md"
    assert "| 名称 | IP |" in out.text
    assert "| FW01 | 10.0.0.1 |" in out.text


def test_csv_tab_separated():
    out = convert("表.csv", "名称\tIP\nFW01\t10.0.0.1".encode("utf-8"))
    assert "| 名称 | IP |" in out.text


def test_csv_pipe_escaped():
    out = convert("表.csv", "名称,备注\nFW01,a|b\n".encode("utf-8"))
    assert "a\\|b" in out.text


def test_xlsx_each_sheet_a_table():
    out = convert("设备.xlsx", _xlsx_bytes({"主表": [["名称", "IP"], ["FW01", "10.0.0.1"]], "附表": [["x"]]}))
    assert out.target_format == "md"
    assert "## 主表" in out.text and "## 附表" in out.text
    assert "| 名称 | IP |" in out.text and "| FW01 | 10.0.0.1 |" in out.text


def test_pdf_passthrough():
    out = convert("手册.pdf", b"%PDF-1.4 fake")
    assert (out.target_format, out.text, out.has_images) == ("pdf", "", False)


def test_unsupported_extension():
    with pytest.raises(ConvertError, match="不支持"):
        convert("程序.exe", b"MZ")


# ---------------------------------------------------------------------------
# md / html 的本地图内嵌
# ---------------------------------------------------------------------------


def test_md_without_images_stays_md():
    out = convert("笔记.md", "# 标题\n\n正文".encode("utf-8"))
    assert (out.target_format, out.has_images) == ("md", False)
    assert out.text.startswith("# 标题")


def test_md_remote_image_stays_md():
    text = "![logo](https://example.com/a.png)"
    out = convert("笔记.md", text.encode("utf-8"))
    assert (out.target_format, out.has_images) == ("md", False)


def test_md_local_image_inlined_as_html():
    text = "前文\n\n![拓扑](images/topo.png)\n\n后文"
    out = convert("笔记.md", text.encode("utf-8"), {"images/topo.png": PNG_1X1})
    assert (out.target_format, out.has_images) == ("html", True)
    assert "data:image/png;base64," in out.text
    assert out.text.startswith("<!DOCTYPE html>")


def test_md_image_matched_by_basename():
    text = "![拓扑](./img/topo.PNG)"
    out = convert("笔记.md", text.encode("utf-8"), {"topo.png": PNG_1X1})
    assert out.target_format == "html"


def test_md_missing_attachment_rejected():
    with pytest.raises(ConvertError, match="未随附"):
        convert("笔记.md", "![拓扑](topo.png)".encode("utf-8"))


def test_html_local_image_inlined():
    text = '<html><body><p>hi</p><img src="a.png"></body></html>'
    out = convert("页面.html", text.encode("utf-8"), {"a.png": PNG_1X1})
    assert (out.target_format, out.has_images) == ("html", True)
    assert "data:image/png;base64," in out.text


def test_html_without_images_kept():
    text = "<html><body><p>hi</p></body></html>"
    out = convert("页面.html", text.encode("utf-8"))
    assert (out.target_format, out.has_images) == ("html", False)
    assert out.text == text


# ---------------------------------------------------------------------------
# docx
# ---------------------------------------------------------------------------


def test_docx_without_images_to_md():
    content = _docx_bytes([("一级标题", "Heading 1"), ("普通段落", None), ("要点", "List Bullet")])
    out = convert("文档.docx", content)
    assert (out.target_format, out.has_images) == ("md", False)
    assert "# 一级标题" in out.text
    assert "普通段落" in out.text
    assert "- 要点" in out.text


def test_docx_table_to_md():
    d = DocxDocument()
    d.add_paragraph("台账")
    table = d.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "名称"
    table.rows[0].cells[1].text = "IP"
    table.rows[1].cells[0].text = "FW01"
    table.rows[1].cells[1].text = "10.0.0.1"
    buf = io.BytesIO()
    d.save(buf)
    out = convert("文档.docx", buf.getvalue())
    assert "| 名称 | IP |" in out.text and "| FW01 | 10.0.0.1 |" in out.text


def test_docx_with_image_to_html():
    content = _docx_bytes([("带图文档", "Heading 1"), ("看图", None)], image=PNG_1X1)
    out = convert("文档.docx", content)
    assert (out.target_format, out.has_images) == ("html", True)
    assert "data:image/png;base64," in out.text
    assert "<h1>带图文档</h1>" in out.text
    assert "<p>看图</p>" in out.text


def test_docx_broken_file_rejected():
    with pytest.raises(ConvertError, match="docx 解析失败"):
        convert("文档.docx", b"not a zip")


# ---------------------------------------------------------------------------
# 样式表损坏免疫（复用 docs.xlsx_io.parse_xlsx 的降级解析）
# ---------------------------------------------------------------------------


def test_xlsx_with_corrupted_styles_survives():
    from tests.docs.test_xlsx_io import _build_xlsx, _corrupt_styles

    # 裸调 openpyxl 会在这种文件上报 TypeError: expected openpyxl.styles.fills.Fill，
    # 转换路径走 parse_xlsx 的降级解析，值与日期都保住
    out = convert("坏样式.xlsx", _corrupt_styles(_build_xlsx()).getvalue())
    assert out.target_format == "md"
    assert "## 数据" in out.text
    assert "甲" in out.text and "2024-01-01" in out.text  # 单元格值与日期都没丢
