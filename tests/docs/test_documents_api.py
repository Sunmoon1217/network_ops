"""`/api/docs/documents/`：上传转换 / 推送 Dify / 索引状态 的接口测试（Dify 侧全部 mock）。"""

import base64

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from docs import dify
from docs.models import Document

LIST_URL = "/api/docs/documents/"
PNG_1X1 = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def _upload(client, content=None, filename="台账.txt", attachments=None):
    content = "设备台账\n".encode("utf-8") if content is None else content
    files = {"file": SimpleUploadedFile(filename, content)}
    if attachments:
        files["attachments"] = [SimpleUploadedFile(n, b) for n, b in attachments.items()]
    return client.post(LIST_URL, files, format="multipart")


@pytest.fixture
def fake_dify(monkeypatch):
    """假 Dify：记录调用参数，返回成功响应。"""
    calls = {}

    def create(filename, content, content_type="application/octet-stream"):
        calls["create"] = (filename, content, content_type)
        return {"document": {"id": "doc-9", "indexing_status": "waiting"}, "batch": "batch-9"}

    def status_rows(batch):
        calls["status_batch"] = batch
        return [{"id": "doc-9", "indexing_status": "completed"}]

    monkeypatch.setattr(dify, "is_configured", lambda: True)
    monkeypatch.setattr(dify, "create_document_by_file", create)
    monkeypatch.setattr(dify, "indexing_status", status_rows)
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
    assert body["has_images"] is False
    assert Document.objects.filter(pk=body["id"], source_file=b"\xe8\xae\xbe\xe5\xa4\x87\xe5\x8f\xb0\xe8\xb4\xa6\n").exists()


def test_upload_md_with_attachment_becomes_html(operator_client):
    resp = _upload(operator_client, "![图](a.png)".encode("utf-8"), "笔记.md", attachments={"a.png": PNG_1X1})
    body = resp.json()
    assert body["target_format"] == "html" and body["has_images"] is True
    assert "data:image/png;base64," in body["converted"]


def test_upload_missing_attachment_rejected(operator_client):
    resp = _upload(operator_client, "![图](a.png)".encode("utf-8"), "笔记.md")
    assert resp.status_code == 400
    assert "未随附" in resp.json()["detail"]
    assert not Document.objects.exists()


def test_upload_unsupported_extension(operator_client):
    resp = _upload(operator_client, b"MZ", "程序.exe")
    assert resp.status_code == 400
    assert not Document.objects.exists()


def test_upload_requires_file(operator_client):
    resp = operator_client.post(LIST_URL, {}, format="multipart")
    assert resp.status_code == 400


def test_upload_pdf_passthrough(operator_client):
    resp = _upload(operator_client, b"%PDF-1.4", "手册.pdf")
    body = resp.json()
    assert (body["source_format"], body["target_format"], body["converted"]) == ("pdf", "pdf", "")


# ---------------------------------------------------------------------------
# 推送 / 状态
# ---------------------------------------------------------------------------


def test_push_markdown_document(operator_client, fake_dify):
    doc_id = _upload(operator_client).json()["id"]
    resp = operator_client.post(f"{LIST_URL}{doc_id}/push/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pushed"
    assert (body["dify_document_id"], body["dify_batch"]) == ("doc-9", "batch-9")
    assert body["pushed_at"] is not None
    filename, content, content_type = fake_dify["create"]
    assert (filename, content_type) == ("台账.md", "text/markdown")
    assert content.decode("utf-8") == "设备台账\n"


def test_push_pdf_uses_source_file(operator_client, fake_dify):
    doc_id = _upload(operator_client, b"%PDF-1.4", "手册.pdf").json()["id"]
    operator_client.post(f"{LIST_URL}{doc_id}/push/")
    filename, content, content_type = fake_dify["create"]
    assert (filename, content_type) == ("手册.pdf", "application/pdf")
    assert content == b"%PDF-1.4"


def test_push_twice_conflicts(operator_client, fake_dify):
    doc_id = _upload(operator_client).json()["id"]
    assert operator_client.post(f"{LIST_URL}{doc_id}/push/").status_code == 200
    assert operator_client.post(f"{LIST_URL}{doc_id}/push/").status_code == 409


def test_push_without_config_unavailable(operator_client, settings):
    settings.DIFY_CONFIG = {**settings.DIFY_CONFIG, "api_key": ""}
    doc_id = _upload(operator_client).json()["id"]
    assert operator_client.post(f"{LIST_URL}{doc_id}/push/").status_code == 503


def test_push_failure_recorded_and_retryable(operator_client, monkeypatch):
    def boom(*args, **kwargs):
        raise dify.DifyError("Dify 返回 500", code="error", status=500)

    monkeypatch.setattr(dify, "is_configured", lambda: True)
    monkeypatch.setattr(dify, "create_document_by_file", boom)
    doc_id = _upload(operator_client).json()["id"]
    resp = operator_client.post(f"{LIST_URL}{doc_id}/push/")
    assert resp.status_code == 502
    doc = Document.objects.get(pk=doc_id)
    assert doc.status == Document.STATUS_PUSH_FAILED and "500" in doc.error
    # 失败后可重推
    monkeypatch.setattr(dify, "create_document_by_file", lambda *a, **k: {"document": {"id": "doc-1", "indexing_status": "waiting"}, "batch": "b-1"})
    assert operator_client.post(f"{LIST_URL}{doc_id}/push/").status_code == 200


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
# 列表 / 详情 / 删除 / 权限
# ---------------------------------------------------------------------------


def test_list_and_detail(operator_client):
    doc_id = _upload(operator_client).json()["id"]
    listing = operator_client.get(LIST_URL).json()["results"]
    assert [d["id"] for d in listing] == [doc_id]
    assert "converted" not in listing[0]  # 列表不带产物
    detail = operator_client.get(f"{LIST_URL}{doc_id}/").json()
    assert detail["converted"] == "设备台账\n"


def test_delete_document(operator_client):
    doc_id = _upload(operator_client).json()["id"]
    assert operator_client.delete(f"{LIST_URL}{doc_id}/").status_code == 204
    assert not Document.objects.exists()


def test_readonly_user_can_read_but_not_write(api_client, operator_client):
    doc_id = _upload(operator_client).json()["id"]
    assert api_client.get(LIST_URL).status_code == 200
    assert api_client.get(f"{LIST_URL}{doc_id}/").status_code == 200
    assert _upload(api_client).status_code == 403
    assert api_client.post(f"{LIST_URL}{doc_id}/push/").status_code == 403
    assert api_client.delete(f"{LIST_URL}{doc_id}/").status_code == 403
