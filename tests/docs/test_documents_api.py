"""`/api/docs/documents/`：上传转换 / 查看下载 / 编辑产物 / 重转 / 历史回滚 /
推送（create/update 两态）的接口测试（Dify 侧全部 mock）。"""

import base64

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from docs import dify
from docs.models import Document, DocumentRevision

LIST_URL = "/api/docs/documents/"
PNG_1X1 = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def _upload(client, content=None, filename="台账.txt", attachments=None):
    content = "设备台账\n".encode("utf-8") if content is None else content
    files = {"file": SimpleUploadedFile(filename, content)}
    if attachments:
        files["attachments"] = [SimpleUploadedFile(n, b) for n, b in attachments.items()]
    return client.post(LIST_URL, files, format="multipart")


def _reconvert(client, doc_id, content=None, filename="新台账.txt"):
    content = "新内容\n".encode("utf-8") if content is None else content
    return client.post(f"{LIST_URL}{doc_id}/reconvert/", {"file": SimpleUploadedFile(filename, content)}, format="multipart")


@pytest.fixture
def fake_dify(monkeypatch):
    """假 Dify：记录调用参数，返回成功响应（create / update × text / file）。"""
    calls = {}
    ok = {"document": {"id": "doc-9", "indexing_status": "waiting"}, "batch": "batch-9"}

    monkeypatch.setattr(dify, "is_configured", lambda: True)
    monkeypatch.setattr(dify, "create_document_by_text", lambda name, text: calls.update(create_text=(name, text)) or ok)
    monkeypatch.setattr(
        dify, "create_document_by_file", lambda filename, content, content_type="application/octet-stream": calls.update(create_file=(filename, content, content_type)) or ok
    )
    monkeypatch.setattr(dify, "update_document_by_text", lambda document_id, name, text: calls.update(update_text=(document_id, name, text)) or {**ok, "batch": "batch-10"})
    monkeypatch.setattr(
        dify,
        "update_document_by_file",
        lambda document_id, filename, content, content_type="application/octet-stream": (
            calls.update(update_file=(document_id, filename, content, content_type)) or {**ok, "batch": "batch-10"}
        ),
    )
    monkeypatch.setattr(dify, "indexing_status", lambda batch: calls.update(status_batch=batch) or [{"id": "doc-9", "indexing_status": "completed"}])
    return calls


# ---------------------------------------------------------------------------
# 上传转换
# ---------------------------------------------------------------------------


def test_upload_converts_to_md(operator_client):
    resp = _upload(operator_client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "台账.txt"
    assert (body["source_format"], body["target_format"], body["status"]) == ("txt", "md", "converted")
    assert body["converted"] == "设备台账\n"
    assert body["latest_revision"] == 1 and body["edited"] is False and body["pending_sync"] is False
    assert DocumentRevision.objects.filter(document_id=body["id"], revision=1, note="初始转换").exists()


def test_upload_md_with_attachment_becomes_html(operator_client):
    body = _upload(operator_client, "![图](a.png)".encode("utf-8"), "笔记.md", attachments={"a.png": PNG_1X1}).json()
    assert body["target_format"] == "html" and body["has_images"] is True
    assert "data:image/png;base64," in body["converted"]


def test_upload_missing_attachment_rejected(operator_client):
    resp = _upload(operator_client, "![图](a.png)".encode("utf-8"), "笔记.md")
    assert resp.status_code == 400
    assert "未随附" in resp.json()["detail"]
    assert not Document.objects.exists()


def test_upload_unsupported_extension(operator_client):
    assert _upload(operator_client, b"MZ", "程序.exe").status_code == 400
    assert not Document.objects.exists()


def test_upload_requires_file(operator_client):
    assert operator_client.post(LIST_URL, {}, format="multipart").status_code == 400


def test_upload_pdf_passthrough(operator_client):
    body = _upload(operator_client, b"%PDF-1.4", "手册.pdf").json()
    assert (body["source_format"], body["target_format"], body["converted"]) == ("pdf", "pdf", "")


# ---------------------------------------------------------------------------
# 查看 / 下载
# ---------------------------------------------------------------------------


def test_list_and_detail(operator_client):
    doc_id = _upload(operator_client).json()["id"]
    listing = operator_client.get(LIST_URL).json()["results"]
    assert [d["id"] for d in listing] == [doc_id]
    assert "converted" not in listing[0]  # 列表不带产物
    detail = operator_client.get(f"{LIST_URL}{doc_id}/").json()
    assert detail["converted"] == "设备台账\n"


def test_download_source_file(operator_client):
    doc_id = _upload(operator_client, b"%PDF-1.4", "手册.pdf").json()["id"]
    resp = operator_client.get(f"{LIST_URL}{doc_id}/download/")
    assert resp.status_code == 200
    assert resp.content == b"%PDF-1.4"
    assert "filename*=UTF-8''%E6%89%8B%E5%86%8C.pdf" in resp["Content-Disposition"]


# ---------------------------------------------------------------------------
# 编辑产物
# ---------------------------------------------------------------------------


def test_edit_converted_lands_revision(operator_client):
    doc_id = _upload(operator_client).json()["id"]
    resp = operator_client.put(f"{LIST_URL}{doc_id}/", {"converted": "改过的产物", "note": "修正标题"}, format="json")
    assert resp.status_code == 201
    body = resp.json()
    assert (body["converted"], body["edited"], body["latest_revision"], body["revision"]) == ("改过的产物", True, 2, 2)
    assert body["pending_sync"] is False  # 未推送过，无同步概念
    rev = DocumentRevision.objects.get(document_id=doc_id, revision=2)
    assert (rev.converted, rev.edited, rev.note) == ("改过的产物", True, "修正标题")


def test_edit_pdf_rejected(operator_client):
    doc_id = _upload(operator_client, b"%PDF-1.4", "手册.pdf").json()["id"]
    resp = operator_client.put(f"{LIST_URL}{doc_id}/", {"converted": "x"}, format="json")
    assert resp.status_code == 400
    assert "重新转换" in resp.json()["detail"]


def test_edit_requires_converted_string(operator_client):
    doc_id = _upload(operator_client).json()["id"]
    assert operator_client.put(f"{LIST_URL}{doc_id}/", {}, format="json").status_code == 400


def test_edit_after_push_marks_pending_sync(operator_client, fake_dify):
    doc_id = _upload(operator_client).json()["id"]
    operator_client.post(f"{LIST_URL}{doc_id}/push/")
    body = operator_client.put(f"{LIST_URL}{doc_id}/", {"converted": "v2"}, format="json").json()
    assert body["pending_sync"] is True and body["status"] == "pushed"


# ---------------------------------------------------------------------------
# 重新转换（替换源文件）
# ---------------------------------------------------------------------------


def test_reconvert_replaces_source_and_lands_revision(operator_client):
    doc_id = _upload(operator_client).json()["id"]
    resp = _reconvert(operator_client, doc_id)
    assert resp.status_code == 201
    body = resp.json()
    assert (body["name"], body["converted"], body["latest_revision"]) == ("新台账.txt", "新内容\n", 2)
    assert body["edited"] is False
    assert bytes(Document.objects.get(pk=doc_id).source_file) == "新内容\n".encode("utf-8")  # BinaryField 取出是 memoryview


def test_reconvert_after_push_marks_pending_sync(operator_client, fake_dify):
    doc_id = _upload(operator_client).json()["id"]
    operator_client.post(f"{LIST_URL}{doc_id}/push/")
    body = _reconvert(operator_client, doc_id).json()
    assert body["pending_sync"] is True


def test_reconvert_keeps_edit_history_rollbackable(operator_client):
    doc_id = _upload(operator_client).json()["id"]
    operator_client.put(f"{LIST_URL}{doc_id}/", {"converted": "人工修改"}, format="json")
    _reconvert(operator_client, doc_id)
    # 人工修改的产物还在 v2 快照里，可回滚
    resp = operator_client.post(f"{LIST_URL}{doc_id}/revisions/2/restore/")
    assert resp.json()["converted"] == "人工修改"


# ---------------------------------------------------------------------------
# 版本历史 / 回滚
# ---------------------------------------------------------------------------


def test_revision_list_and_detail(operator_client):
    doc_id = _upload(operator_client).json()["id"]
    operator_client.put(f"{LIST_URL}{doc_id}/", {"converted": "v2 产物"}, format="json")
    listing = operator_client.get(f"{LIST_URL}{doc_id}/revisions/").json()["results"]
    assert [r["revision"] for r in listing] == [2, 1]
    assert listing[0]["edited"] is True and listing[1]["edited"] is False
    detail = operator_client.get(f"{LIST_URL}{doc_id}/revisions/1/").json()
    assert detail["converted"] == "设备台账\n"


def test_revision_restore_lands_new_version(operator_client):
    doc_id = _upload(operator_client).json()["id"]
    operator_client.put(f"{LIST_URL}{doc_id}/", {"converted": "v2"}, format="json")
    resp = operator_client.post(f"{LIST_URL}{doc_id}/revisions/1/restore/")
    assert resp.status_code == 201
    body = resp.json()
    assert (body["converted"], body["latest_revision"], body["revision"]) == ("设备台账\n", 3, 3)
    assert body["edited"] is False  # 恢复的是转换产出版本
    assert DocumentRevision.objects.filter(document_id=doc_id).count() == 3  # 历史不被改写


# ---------------------------------------------------------------------------
# 推送（create / update 两态）/ 状态
# ---------------------------------------------------------------------------


def test_push_markdown_uses_create_by_text(operator_client, fake_dify):
    doc_id = _upload(operator_client).json()["id"]
    resp = operator_client.post(f"{LIST_URL}{doc_id}/push/")
    assert resp.status_code == 200
    body = resp.json()
    assert (body["status"], body["dify_document_id"], body["dify_batch"]) == ("pushed", "doc-9", "batch-9")
    assert fake_dify["create_text"] == ("台账.md", "设备台账\n")
    assert "create_file" not in fake_dify


def test_push_pdf_uses_create_by_file(operator_client, fake_dify):
    doc_id = _upload(operator_client, b"%PDF-1.4", "手册.pdf").json()["id"]
    operator_client.post(f"{LIST_URL}{doc_id}/push/")
    filename, content, content_type = fake_dify["create_file"]
    assert (filename, content, content_type) == ("手册.pdf", b"%PDF-1.4", "application/pdf")


def test_push_twice_conflicts_without_changes(operator_client, fake_dify):
    doc_id = _upload(operator_client).json()["id"]
    assert operator_client.post(f"{LIST_URL}{doc_id}/push/").status_code == 200
    assert operator_client.post(f"{LIST_URL}{doc_id}/push/").status_code == 409


def test_push_update_after_edit(operator_client, fake_dify):
    doc_id = _upload(operator_client).json()["id"]
    operator_client.post(f"{LIST_URL}{doc_id}/push/")
    operator_client.put(f"{LIST_URL}{doc_id}/", {"converted": "v2 产物"}, format="json")
    resp = operator_client.post(f"{LIST_URL}{doc_id}/push/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["pending_sync"] is False and body["dify_batch"] == "batch-10"
    assert fake_dify["update_text"] == ("doc-9", "台账.md", "v2 产物")
    assert "update_file" not in fake_dify


def test_push_update_pdf_after_reconvert(operator_client, fake_dify):
    doc_id = _upload(operator_client, b"%PDF-1.4", "手册.pdf").json()["id"]
    operator_client.post(f"{LIST_URL}{doc_id}/push/")
    _reconvert(operator_client, doc_id, content=b"%PDF-1.5", filename="手册2.pdf")
    operator_client.post(f"{LIST_URL}{doc_id}/push/")
    document_id, filename, content, content_type = fake_dify["update_file"]
    assert (document_id, filename, content, content_type) == ("doc-9", "手册2.pdf", b"%PDF-1.5", "application/pdf")


def test_push_without_config_unavailable(operator_client, settings):
    settings.DIFY_CONFIG = {**settings.DIFY_CONFIG, "api_key": ""}
    doc_id = _upload(operator_client).json()["id"]
    assert operator_client.post(f"{LIST_URL}{doc_id}/push/").status_code == 503


def test_push_failure_recorded_and_retryable(operator_client, monkeypatch):
    def boom(*args, **kwargs):
        raise dify.DifyError("Dify 返回 500", code="error", status=500)

    monkeypatch.setattr(dify, "is_configured", lambda: True)
    monkeypatch.setattr(dify, "create_document_by_text", boom)
    doc_id = _upload(operator_client).json()["id"]
    resp = operator_client.post(f"{LIST_URL}{doc_id}/push/")
    assert resp.status_code == 502
    doc = Document.objects.get(pk=doc_id)
    assert doc.status == Document.STATUS_PUSH_FAILED and "500" in doc.error
    # 失败后可重推
    monkeypatch.setattr(dify, "create_document_by_text", lambda *a, **k: {"document": {"id": "doc-1", "indexing_status": "waiting"}, "batch": "b-1"})
    assert operator_client.post(f"{LIST_URL}{doc_id}/push/").status_code == 200


def test_update_failure_keeps_pushed_and_pending(operator_client, fake_dify, monkeypatch):
    def boom(*args, **kwargs):
        raise dify.DifyError("Dify 返回 500", code="error", status=500)

    doc_id = _upload(operator_client).json()["id"]
    operator_client.post(f"{LIST_URL}{doc_id}/push/")
    operator_client.put(f"{LIST_URL}{doc_id}/", {"converted": "v2"}, format="json")
    monkeypatch.setattr(dify, "update_document_by_text", boom)
    resp = operator_client.post(f"{LIST_URL}{doc_id}/push/")
    assert resp.status_code == 502
    doc = Document.objects.get(pk=doc_id)
    # 知识库里文档还在（旧版），状态保持 pushed、待同步可重试
    assert doc.status == Document.STATUS_PUSHED and doc.pending_sync is True and "500" in doc.error


def test_status_syncs_indexing(operator_client, fake_dify):
    doc_id = _upload(operator_client).json()["id"]
    operator_client.post(f"{LIST_URL}{doc_id}/push/")
    resp = operator_client.get(f"{LIST_URL}{doc_id}/status/")
    assert resp.status_code == 200
    assert resp.json()["dify_indexing_status"] == "completed"
    assert fake_dify["status_batch"] == "batch-9"


def test_status_before_push_rejected(operator_client):
    doc_id = _upload(operator_client).json()["id"]
    assert operator_client.get(f"{LIST_URL}{doc_id}/status/").status_code == 400


# ---------------------------------------------------------------------------
# 删除 / 权限
# ---------------------------------------------------------------------------


def test_delete_document(operator_client):
    doc_id = _upload(operator_client).json()["id"]
    assert operator_client.delete(f"{LIST_URL}{doc_id}/").status_code == 204
    assert not Document.objects.exists() and not DocumentRevision.objects.exists()


def test_readonly_user_can_read_but_not_write(api_client, operator_client):
    doc_id = _upload(operator_client).json()["id"]
    assert api_client.get(LIST_URL).status_code == 200
    assert api_client.get(f"{LIST_URL}{doc_id}/").status_code == 200
    assert api_client.get(f"{LIST_URL}{doc_id}/download/").status_code == 200
    assert api_client.get(f"{LIST_URL}{doc_id}/revisions/").status_code == 200
    assert _upload(api_client).status_code == 403
    assert api_client.put(f"{LIST_URL}{doc_id}/", {"converted": "x"}, format="json").status_code == 403
    assert _reconvert(api_client, doc_id).status_code == 403
    assert api_client.post(f"{LIST_URL}{doc_id}/revisions/1/restore/").status_code == 403
    assert api_client.post(f"{LIST_URL}{doc_id}/push/").status_code == 403
    assert api_client.delete(f"{LIST_URL}{doc_id}/").status_code == 403
