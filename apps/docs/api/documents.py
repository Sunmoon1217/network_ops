"""文档转换与 Dify 推送接口。

管道两步走（每步独立接口，失败可重试、产物全程留档在库）：

1. ``POST /api/docs/documents/`` 上传转换——主文档 + 可选图片附件（multipart：
   ``file`` + ``attachments``），落库为 ``converted`` 状态（转换失败直接 400，不落记录）；
2. ``POST /api/docs/documents/<id>/push/`` 推送 Dify 知识库（``create-by-file``），
   成功记 dify_document_id / batch；失败落 ``push_failed`` + 错误信息，可重推。

pdf 源文件直传不转换（Dify 原生解析保留版式与图片）。权限走全局默认
``IsOperatorOrReadOnly``：读任何已认证用户可用，写（上传 / 推送 / 删除）限操作员。
"""

from pathlib import Path

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from docs import dify
from docs.convert import MAX_TEXT_BYTES, SOURCE_FORMATS, ConversionResult, ConvertError, convert
from docs.models import Document

_PUSH_CONTENT_TYPES = {"md": "text/markdown", "html": "text/html", "pdf": "application/pdf"}


# ---------------------------------------------------------------------------
# 序列化（响应形状的唯一来源；后端字段将来与前端 types 对账）
# ---------------------------------------------------------------------------


def _summary(doc: Document) -> dict:
    return {
        "id": doc.id,
        "name": doc.name,
        "source_format": doc.source_format,
        "target_format": doc.target_format,
        "has_images": doc.has_images,
        "status": doc.status,
        "error": doc.error,
        "dify_document_id": doc.dify_document_id,
        "dify_batch": doc.dify_batch,
        "dify_indexing_status": doc.dify_indexing_status,
        "pushed_at": doc.pushed_at,
        "created_by": doc.created_by.username if doc.created_by else None,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
    }


def _detail(doc: Document) -> dict:
    return {**_summary(doc), "converted": doc.converted}


# ---------------------------------------------------------------------------
# 内部
# ---------------------------------------------------------------------------


def _read_upload(f) -> bytes:
    if f.size > MAX_TEXT_BYTES:
        raise ConvertError(f"文件超过 {MAX_TEXT_BYTES // (1024 * 1024)}MB 限制")
    return f.read()


def _push_payload(doc: Document) -> tuple[str, bytes, str]:
    """推送内容：pdf 直传源文件，其余推转换产物。返回 (文件名, 字节, content_type)。"""
    if doc.target_format == "pdf":
        return doc.name, bytes(doc.source_file), _PUSH_CONTENT_TYPES["pdf"]
    stem = Path(doc.name).stem or doc.name
    return f"{stem}.{doc.target_format}", doc.converted.encode("utf-8"), _PUSH_CONTENT_TYPES[doc.target_format]


# ---------------------------------------------------------------------------
# 接口
# ---------------------------------------------------------------------------


@api_view(["GET", "POST"])
def document_list(request):
    """文档列表（不含转换产物）/ 上传转换。"""
    if request.method == "GET":
        return Response({"results": [_summary(d) for d in Document.objects.all()]})

    f = request.FILES.get("file")
    if not f:
        return Response({"detail": "请上传文件（file 字段）"}, status=status.HTTP_400_BAD_REQUEST)
    fmt = str(f.name).rsplit(".", 1)[-1].lower() if "." in str(f.name) else ""
    if fmt not in SOURCE_FORMATS:
        return Response({"detail": f"不支持的文件格式：.{fmt or '(无扩展名)'}，支持 {'/'.join(sorted(SOURCE_FORMATS))}"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        content = _read_upload(f)
        attachments = {}
        for att in request.FILES.getlist("attachments"):
            attachments[str(att.name).lower()] = _read_upload(att)
        result: ConversionResult = convert(str(f.name), content, attachments)
    except ConvertError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    doc = Document.objects.create(
        name=str(f.name)[:255],
        source_format=fmt,
        target_format=result.target_format,
        source_file=content,
        converted=result.text,
        has_images=result.has_images,
        created_by=request.user,
        updated_by=request.user,
    )
    return Response(_detail(doc), status=status.HTTP_201_CREATED)


@api_view(["GET", "DELETE"])
def document_detail(request, pk):
    """文档详情（含转换产物，供预览）/ 删除。"""
    doc = get_object_or_404(Document, pk=pk)
    if request.method == "DELETE":
        doc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    return Response(_detail(doc))


@api_view(["POST"])
def document_push(request, pk):
    """推送 Dify 知识库（幂等保护：已推送返回 409，删除重建可绕过）。"""
    doc = get_object_or_404(Document, pk=pk)
    if doc.status == Document.STATUS_PUSHED:
        return Response({"detail": "文档已推送过 Dify 知识库"}, status=status.HTTP_409_CONFLICT)
    if not dify.is_configured():
        return Response({"detail": "Dify 未配置（DIFY_API_BASE_URL / DIFY_API_KEY / DIFY_DATASET_ID）"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    filename, content, content_type = _push_payload(doc)
    try:
        body = dify.create_document_by_file(filename, content, content_type)
    except dify.DifyError as e:
        doc.status = Document.STATUS_PUSH_FAILED
        doc.error = str(e)[:2000]
        doc.updated_by = request.user
        doc.save(update_fields=["status", "error", "updated_by", "updated_at"])
        return Response({"detail": f"推送 Dify 失败：{e}"}, status=status.HTTP_502_BAD_GATEWAY)

    created = body.get("document") or {}
    with transaction.atomic():
        doc.status = Document.STATUS_PUSHED
        doc.error = ""
        doc.dify_document_id = str(created.get("id") or "")[:64]
        doc.dify_batch = str(body.get("batch") or "")[:64]
        doc.dify_indexing_status = str(created.get("indexing_status") or "")[:32]
        doc.pushed_at = timezone.now()
        doc.updated_by = request.user
        doc.save(update_fields=["status", "error", "dify_document_id", "dify_batch", "dify_indexing_status", "pushed_at", "updated_by", "updated_at"])
    return Response(_detail(doc))


@api_view(["GET"])
def document_status(request, pk):
    """从 Dify 同步索引进度（waiting / indexing / completed / error）。"""
    doc = get_object_or_404(Document, pk=pk)
    if doc.status != Document.STATUS_PUSHED:
        return Response({"detail": "文档尚未推送，无索引状态可查"}, status=status.HTTP_400_BAD_REQUEST)
    if not dify.is_configured():
        return Response({"detail": "Dify 未配置（DIFY_API_BASE_URL / DIFY_API_KEY / DIFY_DATASET_ID）"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    try:
        rows = dify.indexing_status(doc.dify_batch)
    except dify.DifyError as e:
        return Response({"detail": f"查询 Dify 索引状态失败：{e}"}, status=status.HTTP_502_BAD_GATEWAY)
    if rows:
        doc.dify_indexing_status = str(rows[0].get("indexing_status") or "")[:32]
        doc.save(update_fields=["dify_indexing_status", "updated_at"])
    return Response(_detail(doc))
