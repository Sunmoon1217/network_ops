"""文档转换：上传的文本文件 → md 或 自包含 html（含图时），pdf 直传。

Dify 知识库 ``document/create-by-file`` **一次只收一个文件**（多文件报 too_many_files），
所以「图片不能和 md 一起分开上传」——含图文档统一转成 **base64 内嵌的自包含 html**
单文件推送，这就是「有图 → html」规则的由来。

转换规则（``convert()`` 唯一入口）::

    txt      → md（UTF-8 / GB18030 自适应解码）
    md       → md；引用的本地图片随附上传后内嵌 → 自包含 html
    docx     → md；含内嵌图片 → 自包含 html（base64 内嵌）
    html/htm → html（本地图片引用随附上传后 base64 内嵌；无图原样保留）
    xlsx     → md（每 sheet：网格表 + 行式键值「行记录」双写）
    csv      → md（网格表 + 行式键值「行记录」双写）
    pdf      → 直传（不转换；Dify 原生解析保留版式与图片）

表格**双写**的由来：Dify 的分段是「分隔符 + max_tokens」机械切分、不认表格结构
（社区有 content-aware chunker 专门绕这一点）——大表网格会被拦腰切、表头留在
上一个 chunk，行碎片 `| 甲 | 1 |` 缺列名语义，向量/关键词检索都吃亏。「行记录」
段落每行自带「列名：值」、天然抗分段切断，网格表保留给人看与编辑。

md / html 里引用**本地图片**（相对路径或裸文件名）时，图片必须随附上传
（接口的 attachments 字段）：引用全部能解析到 → 内嵌；解析不到 → 转换报错，
不静默产出缺图的文档。http(s) / data: 远程引用不内嵌、原样保留。
"""

import base64
import csv
import io
import mimetypes
import re
from dataclasses import dataclass
from typing import Any, cast

import markdown as markdown_lib
from docx import Document as DocxDocumentFactory
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph as DocxParagraph

TEXT_FORMATS = {"txt", "md", "docx", "html", "htm", "xlsx", "csv"}
SOURCE_FORMATS = TEXT_FORMATS | {"pdf"}
MAX_TEXT_BYTES = 32 * 1024 * 1024  # 与接口层上传限长一致（产物进 TextField / BinaryField）

_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(\s*([^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
_HTML_IMG_RE = re.compile(r"<img\b[^>]*?src\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)


class ConvertError(ValueError):
    """转换失败（格式不支持 / 内容解码失败 / 引用的本地图片未随附）。"""


@dataclass
class ConversionResult:
    target_format: str  # md / html / pdf
    text: str  # 转换产物（pdf 直传为空字符串，内容仍在 source_file）
    has_images: bool  # 产物是否内嵌了图片


# ---------------------------------------------------------------------------
# 公共入口
# ---------------------------------------------------------------------------


def convert(name: str, content: bytes, attachments: dict[str, bytes] | None = None) -> ConversionResult:
    """按文件扩展名分发转换。``attachments``：随附图片（文件名小写 → 字节）。"""
    if len(content) > MAX_TEXT_BYTES:
        raise ConvertError(f"文件超过 {MAX_TEXT_BYTES // (1024 * 1024)}MB 限制")
    fmt = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if fmt not in SOURCE_FORMATS:
        raise ConvertError(f"不支持的文件格式：.{fmt or '(无扩展名)'}，支持 {'/'.join(sorted(SOURCE_FORMATS))}")
    atts = {k.lower(): v for k, v in (attachments or {}).items()}

    if fmt == "pdf":
        return ConversionResult("pdf", "", False)
    if fmt == "txt":
        return ConversionResult("md", _decode_text(content), False)
    if fmt == "csv":
        return ConversionResult("md", _csv_to_md(_decode_text(content)), False)
    if fmt == "xlsx":
        return ConversionResult("md", _xlsx_to_md(content), False)
    if fmt == "md":
        return _convert_md(_decode_text(content), atts)
    if fmt in ("html", "htm"):
        return _convert_html(_decode_text(content), atts)
    return _convert_docx(content, atts)  # docx


# ---------------------------------------------------------------------------
# 文本解码与表格 → md
# ---------------------------------------------------------------------------


def _decode_text(raw: bytes) -> str:
    """UTF-8（含 BOM）优先，失败回退 GB18030（运维侧老文件常见），都不行才报错。"""
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ConvertError("文本解码失败：既不是 UTF-8 也不是 GB18030")


def _cell_text(value) -> str:
    return str(value if value is not None else "").replace("\n", " ").strip()


def _escape_cell(value) -> str:
    return _cell_text(value).replace("|", "\\|")


def _rows_to_md(rows: list[list]) -> str:
    rows = [[_escape_cell(c) for c in row] for row in rows]
    rows = [row for row in rows if any(row)]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    header, body = rows[0], rows[1:]
    lines = ["| " + " | ".join(header) + " |", "|" + " --- |" * width]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines)


def _rows_to_records(rows: list[list]) -> str:
    """行式键值展开（检索用）：每行一条「列名：值」记录，自带表头语义、抗分段切断。

    首行是表头（与 :func:`_rows_to_md` 同口径）；空值格跳过、空表头回退「列N」。
    """
    norm = [[_cell_text(c) for c in row] for row in rows]
    norm = [row for row in norm if any(row)]
    if len(norm) < 2:
        return ""
    header, body = norm[0], norm[1:]
    lines = []
    for row in body:
        pairs = []
        for i, value in enumerate(row):
            if not value:
                continue
            name = header[i] if i < len(header) and header[i] else f"列{i + 1}"
            pairs.append(f"{name}：{value}")
        if pairs:
            lines.append("- " + "；".join(pairs))
    return "\n".join(lines)


def _tabular_md(rows: list[list]) -> str:
    """表格双写：网格表（人看/可编辑）+ 行记录（检索），两段之间空行。"""
    parts = []
    table = _rows_to_md(rows)
    if table:
        parts.append(table)
    records = _rows_to_records(rows)
    if records:
        parts.append("行记录：\n" + records)
    return "\n\n".join(parts)


def _csv_to_md(text: str) -> str:
    sample = text[:4096]
    delimiter = "\t" if ("\t" in sample and "," not in sample) else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    return _tabular_md(rows)


def _xlsx_to_md(content: bytes) -> str:
    from docs import xlsx_io  # 本地导入：openpyxl 启动慢，仅 xlsx 路径需要

    # 走 parse_xlsx 而不是裸调 openpyxl：它带「样式表损坏免疫」（降级跳过样式、
    # 自扫 numFmt 保日期）与合并单元格填充——裸调会在坏 styles.xml 上整个判死
    # （TypeError: expected <class 'openpyxl.styles.fills.Fill'>）。
    try:
        data = xlsx_io.parse_xlsx(io.BytesIO(content))
    except Exception as e:
        raise ConvertError(f"xlsx 解析失败：{e}") from e
    parts = []
    for sheet in data.get("sheets") or []:
        name = str(sheet.get("name") or "")
        body = _tabular_md(sheet.get("rows") or [])
        parts.append(f"## {name}\n\n{body}" if body else f"## {name}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# 本地图片引用解析
# ---------------------------------------------------------------------------


def _is_remote(ref: str) -> bool:
    return ref.lower().startswith(("http://", "https://", "data:", "mailto:"))


def _resolve_image(ref: str, atts: dict[str, bytes]) -> bytes | None:
    """引用路径 → 随附图片字节：去掉 query/fragment，按全路径 / 裸文件名（大小写不敏感）匹配。"""
    key = ref.split("?")[0].split("#")[0].replace("\\", "/").strip()
    for candidate in (key, key.rsplit("/", 1)[-1]):
        hit = atts.get(candidate.lower())
        if hit is not None:
            return hit
    return None


def _data_uri(filename: str, blob: bytes, content_type: str | None = None) -> str:
    mime = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(blob).decode('ascii')}"


def _inline_local_images(text: str, atts: dict[str, bytes], is_html: bool) -> tuple[str, bool]:
    """把文本里的本地图引用换成 data URI；返回 (新文本, 是否有图)。解析不到即报错。"""
    missing: list[str] = []
    found = False
    patterns = [_HTML_IMG_RE] if is_html else [_MD_IMAGE_RE, _HTML_IMG_RE]

    def repl(match: re.Match) -> str:
        nonlocal found
        ref = match.group(1)
        if _is_remote(ref):
            return match.group(0)
        blob = _resolve_image(ref, atts)
        if blob is None:
            missing.append(ref)
            return match.group(0)
        found = True
        return match.group(0).replace(ref, _data_uri(ref, blob), 1)

    for pat in patterns:
        text = pat.sub(repl, text)
    if missing:
        raise ConvertError("引用的本地图片未随附上传：" + "、".join(sorted(set(missing))))
    return text, found


# ---------------------------------------------------------------------------
# md / html 转换
# ---------------------------------------------------------------------------


def render_preview(text: str, target_format: str) -> str:
    """查看用渲染：md 交给 markdown 库渲成 html（与转换同一套渲染），html 原样。

    只用于**预览**（前端沙箱 iframe 展示），不落库、不影响推送产物。
    """
    if target_format == "html":
        return text
    return _wrap_html("文档", markdown_lib.markdown(text, extensions=["tables", "fenced_code"]))


def _wrap_html(title: str, body: str) -> str:
    escaped = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<!DOCTYPE html>\n<html>\n<head>\n<meta charset="utf-8">\n<title>{escaped}</title>\n</head>\n<body>\n{body}\n</body>\n</html>\n'


def _convert_md(text: str, atts: dict[str, bytes]) -> ConversionResult:
    text, found = _inline_local_images(text, atts, is_html=False)
    if not found:
        return ConversionResult("md", text, False)
    body = markdown_lib.markdown(text, extensions=["tables", "fenced_code"])
    return ConversionResult("html", _wrap_html("文档", body), True)


def _convert_html(text: str, atts: dict[str, bytes]) -> ConversionResult:
    text, found = _inline_local_images(text, atts, is_html=True)
    return ConversionResult("html", text, found)


# ---------------------------------------------------------------------------
# docx 转换：块级中间结构（段落 / 表格 / 图片）→ md 或 html
# ---------------------------------------------------------------------------


def _docx_blocks(doc: DocxDocument):
    """按文档顺序产出块：``("heading", level, runs)`` / ``("para", runs)`` /
    ``("table", rows)`` / ``("image", filename, blob)``；runs 是 (文本, 粗, 斜) 列表。"""
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            para = DocxParagraph(child, doc)
            runs = [(r.text or "", bool(r.bold), bool(r.italic)) for r in para.runs]
            for blob, filename in _para_images(para, doc):
                yield ("image", filename, blob)
            style = (para.style.name or "") if para.style is not None else ""
            if style.startswith("Heading"):
                try:
                    level = int(style.split()[-1])
                except ValueError:
                    level = 1
                yield ("heading", min(max(level, 1), 6), runs)
            elif style.startswith("List"):
                # 列表段落：首段文字前缀列表标记（有序/无序按样式名判断）
                marker = "1. " if "number" in style.lower() else "- "
                runs = [(marker + t if i == 0 else t, b, it) for i, (t, b, it) in enumerate(runs)] or [(marker, False, False)]
                yield ("para", runs)
            elif runs:
                yield ("para", runs)
        elif child.tag == qn("w:tbl"):
            table = DocxTable(child, doc)
            yield ("table", [[c.text or "" for c in row.cells] for row in table.rows])


# OOXML 命名空间的 Clark 记法（python-docx 的元素 xpath 不收 namespaces 参数，直接 iter 找）
_NS_A_BLIP = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
_NS_V_IMAGEDATA = "{urn:schemas-microsoft-com:vml}imagedata"
_NS_R_EMBED = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
_NS_R_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _para_images(para: DocxParagraph, doc: DocxDocument):
    """段落内嵌图片（w:drawing 的 a:blip 与旧式 w:pict 的 v:imagedata 都认）。"""
    element = para._p
    refs = [node.get(_NS_R_EMBED) for node in element.iter(_NS_A_BLIP)]
    refs += [node.get(_NS_R_ID) for node in element.iter(_NS_V_IMAGEDATA)]
    for rid in refs:
        if not rid:
            continue
        part = doc.part.related_parts.get(rid)
        blob = getattr(part, "blob", None)
        if blob:
            filename = str(getattr(part, "partname", "image")).rsplit("/", 1)[-1]
            yield blob, filename


def _runs_to_md(runs) -> str:
    out = []
    for text, bold, italic in runs:
        s = text
        if italic:
            s = f"*{s}*"
        if bold:
            s = f"**{s}**"
        out.append(s)
    return "".join(out).rstrip()


def _html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _runs_to_html(runs) -> str:
    out = []
    for text, bold, italic in runs:
        s = _html_escape(text)
        if italic:
            s = f"<em>{s}</em>"
        if bold:
            s = f"<strong>{s}</strong>"
        out.append(s)
    return "".join(out).rstrip()


def _convert_docx(content: bytes, atts: dict[str, bytes]) -> ConversionResult:
    try:
        doc = DocxDocumentFactory(io.BytesIO(content))
    except Exception as e:
        raise ConvertError(f"docx 解析失败：{e}") from e

    # 块是四种异构元组（见 _docx_blocks docstring），消费端按 kind 分支后整块取字段
    blocks = cast(list[tuple[Any, ...]], list(_docx_blocks(doc)))
    has_images = any(b[0] == "image" for b in blocks)
    if not has_images:
        lines = []
        for block in blocks:
            kind = block[0]
            if kind == "heading":
                lines.append("#" * block[1] + " " + _runs_to_md(block[2]))
            elif kind == "para":
                lines.append(_runs_to_md(block[1]))
            elif kind == "table":
                lines.append(_rows_to_md(block[1]))
        return ConversionResult("md", "\n\n".join(line for line in lines if line).strip(), False)

    parts = []
    for block in blocks:
        kind = block[0]
        if kind == "heading":
            level, runs = block[1], block[2]
            parts.append(f"<h{level}>{_runs_to_html(runs)}</h{level}>")
        elif kind == "para":
            parts.append(f"<p>{_runs_to_html(block[1])}</p>")
        elif kind == "table":
            rows = [[_html_escape(c) for c in row] for row in block[1]]
            header = rows[0] if rows else []
            body = rows[1:] if len(rows) > 1 else []
            th = "".join(f"<th>{c}</th>" for c in header)
            trs = [f"<tr>{''.join(f'<td>{c}</td>' for c in row)}</tr>" for row in body]
            parts.append(f"<table><thead><tr>{th}</tr></thead><tbody>{''.join(trs)}</tbody></table>")
        elif kind == "image":
            _, filename, blob = block
            parts.append(f'<p><img src="{_data_uri(filename, blob)}" alt="{filename}"/></p>')
    return ConversionResult("html", _wrap_html("文档", "\n".join(parts)), True)
