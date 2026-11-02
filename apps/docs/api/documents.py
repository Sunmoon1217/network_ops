"""文档转换与 Dify 推送接口。

管道三步走（每步独立接口，产物全程留档在库、版本可回滚）：

1. ``POST /api/docs/documents/`` 上传转换——主文档 + 可选图片附件（multipart：
   ``file`` + ``attachments``），落 ``converted`` 状态与 v1 版本快照（转换失败
   直接 400，不落记录）；
2. 修改：``PUT /api/docs/documents/<id>/`` 编辑转换产物文本，或
   ``POST /api/docs/documents/<id>/reconvert/`` 替换源文件重新转换——都落新版本
   快照（``DocumentRevision``），已推送文档标记 ``pending_sync`` 等待重推；
3. ``POST /api/docs/documents/<id>/push/`` 推送 Dify 知识库：未推送走
   create（md/html 用 create_by_text、pdf 用 create-by-file），已推送且有
   待同步修改走 **update 原地更新**（update_by-text / update-by-file，不产生
   重复文档）。

另有查看与历史：``GET .../download/`` 源文件下载、``.../revisions/`` 版本列表 /
快照详情 / 回滚（恢复以新版本落地）。pdf 源文件直传不转换，无产物可编辑——
改内容只能替换源文件重新转换。权限走全局默认 ``IsOperatorOrReadOnly``：读任何
已认证用户可用，写（上传 / 编辑 / 重转 / 推送 / 回滚 / 删除）限操作员。
"""

from pathlib import Path
from urllib.parse import quote

from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from docs import dify
from docs.convert import MAX_TEXT_BYTES, SOURCE_FORMATS, ConversionResult, ConvertError, convert
from docs.models import Document, DocumentRevision

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
        "edited": doc.edited,
        "pending_sync": doc.pending_sync,
        "latest_revision": doc.latest_revision,
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


def _revision_summary(rev: DocumentRevision) -> dict:
    return {
        "id": rev.id,
        "revision": rev.revision,
        "note": rev.note,
        "target_format": rev.target_format,
        "has_images": rev.has_images,
        "edited": rev.edited,
        "created_by": rev.created_by.username if rev.created_by else None,
        "created_at": rev.created_at,
    }


def _revision_detail(rev: DocumentRevision) -> dict:
    return {**_revision_summary(rev), "converted": rev.converted}


# ---------------------------------------------------------------------------
# 内部
# ---------------------------------------------------------------------------


def _read_upload(f) -> bytes:
    if f.size > MAX_TEXT_BYTES:
        raise ConvertError(f"文件超过 {MAX_TEXT_BYTES // (1024 * 1024)}MB 限制")
    return f.read()


def _push_name(doc: Document) -> str:
    """推送用文件名：产物是 md/html 时换成产物扩展名，pdf 直传用原名。"""
    if doc.target_format == "pdf":
        return doc.name
    stem = Path(doc.name).stem or doc.name
    return f"{stem}.{doc.target_format}"


def _push_payload(doc: Document) -> tuple[str, bytes, str]:
    """推送内容：pdf 直传源文件，其余推转换产物。返回 (文件名, 字节, content_type)。"""
    if doc.target_format == "pdf":
        return doc.name, bytes(doc.source_file), _PUSH_CONTENT_TYPES["pdf"]
    return _push_name(doc), doc.converted.encode("utf-8"), _PUSH_CONTENT_TYPES[doc.target_format]


def _apply_revision(
    doc: Document, note: str, user, *, edited: bool, converted: str | None = None, target_format: str | None = None, has_images: bool | None = None
) -> DocumentRevision:
    """落一份新版本快照并推进文档状态（回滚也走这里，历史不被改写）。

    产物变更后：已推送文档标 ``pending_sync``（等手动重推 update）；``edited``
    只反映本次动作（人工编辑 / 恢复到人工版本 = True，转换产出 = False）。
    """
    with transaction.atomic():
        if converted is not None:
            doc.converted = converted
        if target_format is not None:
            doc.target_format = target_format
        if has_images is not None:
            doc.has_images = has_images
        doc.edited = edited
        if doc.status == Document.STATUS_PUSHED:
            doc.pending_sync = True
        doc.latest_revision += 1
        doc.updated_by = user
        doc.save()
        rev = DocumentRevision.objects.create(
            document=doc,
            revision=doc.latest_revision,
            note=note[:200],
            converted=doc.converted,
            target_format=doc.target_format,
            has_images=doc.has_images,
            edited=edited,
            created_by=user,
        )
    return rev


def _note(request) -> str:
    return str(request.data.get("note") or "").strip()[:200]


# ---------------------------------------------------------------------------
# 上传 / 列表 / 详情 / 编辑 / 下载 / 删除
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

    with transaction.atomic():
        doc = Document.objects.create(
            name=str(f.name)[:255],
            source_format=fmt,
            target_format=result.target_format,
            source_file=content,
            converted=result.text,
            has_images=result.has_images,
            latest_revision=1,
            created_by=request.user,
            updated_by=request.user,
        )
        DocumentRevision.objects.create(
            document=doc,
            revision=1,
            note="初始转换",
            converted=result.text,
            target_format=result.target_format,
            has_images=result.has_images,
            edited=False,
            created_by=request.user,
        )
    return Response(_detail(doc), status=status.HTTP_201_CREATED)


@api_view(["GET", "PUT", "DELETE"])
def document_detail(request, pk):
    """文档详情（含转换产物，供查看/编辑）/ 编辑产物 / 删除。"""
    doc = get_object_or_404(Document, pk=pk)
    if request.method == "DELETE":
        doc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    if request.method == "GET":
        return Response(_detail(doc))

    if doc.target_format == "pdf":
        return Response({"detail": "pdf 直传没有转换产物可编辑，请用重新转换替换源文件"}, status=status.HTTP_400_BAD_REQUEST)
    converted = request.data.get("converted")
    if not isinstance(converted, str):
        return Response({"detail": "converted 必须是字符串"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        rev = _apply_revision(doc, _note(request) or "编辑产物", request.user, edited=True, converted=converted)
    except IntegrityError:
        return Response({"detail": "保存冲突：其他会话刚保存过，请刷新后重试"}, status=status.HTTP_409_CONFLICT)
    return Response({**_detail(doc), "revision": rev.revision}, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def document_download(request, pk):
    """源文件下载（docx/pdf 等原文件留档）。"""
    doc = get_object_or_404(Document, pk=pk)
    response = HttpResponse(bytes(doc.source_file), content_type="application/octet-stream")
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(doc.name)}"
    return response


# ---------------------------------------------------------------------------
# 重新转换（替换源文件）
# ---------------------------------------------------------------------------


@api_view(["POST"])
def document_reconvert(request, pk):
    """替换源文件并重新转换（产物落新版本；已推送文档标记待同步）。

    人工编辑过的产物会被新转换覆盖——但旧产物还在版本历史里，可回滚。
    """
    doc = get_object_or_404(Document, pk=pk)
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

    try:
        with transaction.atomic():
            doc.name = str(f.name)[:255]
            doc.source_format = fmt
            doc.source_file = content
            doc.converted = result.text
            doc.target_format = result.target_format
            doc.has_images = result.has_images
            doc.save()
            rev = _apply_revision(doc, _note(request) or "重新转换", request.user, edited=False)
    except IntegrityError:
        return Response({"detail": "保存冲突：其他会话刚保存过，请刷新后重试"}, status=status.HTTP_409_CONFLICT)
    return Response({**_detail(doc), "revision": rev.revision}, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# 版本历史
# ---------------------------------------------------------------------------


@api_view(["GET"])
def revision_list(request, pk):
    """版本历史列表（新版本在前）。"""
    doc = get_object_or_404(Document, pk=pk)
    return Response({"results": [_revision_summary(rev) for rev in doc.revisions.all()]})


@api_view(["GET"])
def revision_detail(request, pk, revision):
    """单个版本：产物全量快照。"""
    doc = get_object_or_404(Document, pk=pk)
    rev = get_object_or_404(DocumentRevision, document=doc, revision=revision)
    return Response(_revision_detail(rev))


@api_view(["POST"])
def revision_restore(request, pk, revision):
    """回滚到指定版本（以一次新版本落地，历史不被改写；已推送文档标记待同步）。"""
    doc = get_object_or_404(Document, pk=pk)
    target = get_object_or_404(DocumentRevision, document=doc, revision=revision)
    try:
        rev = _apply_revision(
            doc,
            _note(request) or f"恢复到版本 {target.revision}",
            request.user,
            edited=target.edited,
            converted=target.converted,
            target_format=target.target_format,
            has_images=target.has_images,
        )
    except IntegrityError:
        return Response({"detail": "保存冲突：其他会话刚保存过，请刷新后重试"}, status=status.HTTP_409_CONFLICT)
    return Response({**_detail(doc), "revision": rev.revision}, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# 推送 Dify（create / update 两态）与索引状态
# ---------------------------------------------------------------------------


@api_view(["POST"])
def document_push(request, pk):
    """推送 Dify 知识库：未推送 create；已推送且 pending_sync 时 **update 原地更新**。

    已推送且无待同步修改返回 409（幂等保护）；更新失败保持 pending_sync 可重试。
    """
    doc = get_object_or_404(Document, pk=pk)
    if doc.status == Document.STATUS_PUSHED and not doc.pending_sync:
        return Response({"detail": "文档已推送且无待同步修改"}, status=status.HTTP_409_CONFLICT)
    if not dify.is_configured():
        return Response({"detail": "Dify 未配置（DIFY_API_BASE_URL / DIFY_API_KEY / DIFY_DATASET_ID）"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    is_update = doc.status == Document.STATUS_PUSHED
    filename, content, content_type = _push_payload(doc)
    try:
        if is_update:
            if doc.target_format == "pdf":
                body = dify.update_document_by_file(doc.dify_document_id, filename, content, content_type)
            else:
                body = dify.update_document_by_text(doc.dify_document_id, filename, content.decode("utf-8"))
        elif doc.target_format == "pdf":
            body = dify.create_document_by_file(filename, content, content_type)
        else:
            body = dify.create_document_by_text(filename, content.decode("utf-8"))
    except dify.DifyError as e:
        if is_update:
            # 知识库里仍是旧版（文档还在），只记错误、保持待同步等重试
            doc.error = str(e)[:2000]
            doc.updated_by = request.user
            doc.save(update_fields=["error", "updated_by", "updated_at"])
            return Response({"detail": f"更新 Dify 失败：{e}"}, status=status.HTTP_502_BAD_GATEWAY)
        doc.status = Document.STATUS_PUSH_FAILED
        doc.error = str(e)[:2000]
        doc.updated_by = request.user
        doc.save(update_fields=["status", "error", "updated_by", "updated_at"])
        return Response({"detail": f"推送 Dify 失败：{e}"}, status=status.HTTP_502_BAD_GATEWAY)

    created = body.get("document") or {}
    with transaction.atomic():
        doc.status = Document.STATUS_PUSHED
        doc.error = ""
        doc.pending_sync = False
        doc.dify_document_id = str(created.get("id") or doc.dify_document_id or "")[:64]
        doc.dify_batch = str(body.get("batch") or "")[:64]
        doc.dify_indexing_status = str(created.get("indexing_status") or "")[:32]
        doc.pushed_at = timezone.now()
        doc.updated_by = request.user
        doc.save()
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
