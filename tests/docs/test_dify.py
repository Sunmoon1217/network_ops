"""docs.dify 客户端测试：请求形状（URL / Bearer / multipart）与错误映射，全部 mock 网络。"""

import json

import pytest
from django.test import override_settings

from docs import dify

CFG = {"api_base_url": "https://dify.example.com/v1", "api_key": "sk-test", "dataset_id": "ds-1", "indexing_technique": "high_quality", "timeout": 5}


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def test_not_configured_when_missing_bits():
    with override_settings(DIFY_CONFIG={**CFG, "dataset_id": ""}):
        assert dify.is_configured() is False
        with pytest.raises(dify.DifyError, match="未配置"):
            dify.create_document_by_file("a.md", b"x")


@override_settings(DIFY_CONFIG=CFG)
def test_create_document_request_shape(monkeypatch):
    seen = {}

    def fake_request(method, url, headers=None, timeout=None, **kwargs):
        seen.update(method=method, url=url, headers=headers, timeout=timeout, **kwargs)
        return _Resp(200, {"document": {"id": "doc-1", "indexing_status": "waiting"}, "batch": "b-1"})

    monkeypatch.setattr("docs.dify.requests.request", fake_request)
    body = dify.create_document_by_file("报告.md", "内容".encode("utf-8"), "text/markdown")

    assert body["batch"] == "b-1"
    assert seen["method"] == "POST"
    assert seen["url"] == "https://dify.example.com/v1/datasets/ds-1/document/create-by-file"
    assert seen["headers"] == {"Authorization": "Bearer sk-test"}
    assert seen["timeout"] == 5
    data = json.loads(seen["data"]["data"])
    assert data["indexing_technique"] == "high_quality"
    assert data["process_rule"] == {"mode": "automatic"}
    filename, content, content_type = seen["files"]["file"]
    assert (filename, content, content_type) == ("报告.md", "内容".encode("utf-8"), "text/markdown")


@override_settings(DIFY_CONFIG=CFG)
def test_indexing_status(monkeypatch):
    def fake_request(method, url, **kwargs):
        assert method == "GET"
        assert url.endswith("/datasets/ds-1/documents/b-1/indexing-status")
        return _Resp(200, {"data": [{"id": "doc-1", "indexing_status": "completed"}]})

    monkeypatch.setattr("docs.dify.requests.request", fake_request)
    rows = dify.indexing_status("b-1")
    assert rows[0]["indexing_status"] == "completed"


@override_settings(DIFY_CONFIG=CFG)
def test_error_mapped_with_dify_code(monkeypatch):
    def fake_request(*args, **kwargs):
        return _Resp(413, {"code": "file_too_large", "message": "File size exceeded."})

    monkeypatch.setattr("docs.dify.requests.request", fake_request)
    with pytest.raises(dify.DifyError) as exc:
        dify.create_document_by_file("a.pdf", b"x", "application/pdf")
    assert exc.value.code == "file_too_large"
    assert exc.value.status == 413
    assert "File size exceeded." in str(exc.value)


@override_settings(DIFY_CONFIG=CFG)
def test_network_error_wrapped(monkeypatch):
    import requests as requests_lib

    def fake_request(*args, **kwargs):
        raise requests_lib.ConnectionError("refused")

    monkeypatch.setattr("docs.dify.requests.request", fake_request)
    with pytest.raises(dify.DifyError, match="请求失败"):
        dify.indexing_status("b-1")
