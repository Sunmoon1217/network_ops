"""Dify 知识库 API 客户端（datasets / document）。

对接自托管 Dify 的「知识库 API」（``{DIFY_API_BASE_URL}/datasets/...``，
鉴权 ``Authorization: Bearer {DIFY_API_KEY}``）：

- 建文档：``create_document_by_text``（``document/create_by_text``）/
  ``create_document_by_file``（``document/create-by-file``，multipart：``file``
  + ``data`` JSON，**一次只收一个文件**）——路径下划线/连字符混用是 Dify 官方
  接口原样，别"顺手统一"；
- 更新已推送文档：``update_document_by_text`` / ``update_document_by_file``
  （``documents/{document_id}/update_by-text`` / ``update-by-file``）——按
  document_id **原地更新**，不产生重复文档；
- ``indexing_status``：``GET /datasets/{dataset_id}/documents/{batch}/indexing-status``
  （索引进度：waiting / indexing / completed / error）。

配置来自 ``settings.DIFY_CONFIG``（env 注入，见 base.py 注释）；三项
（api_base_url / api_key / dataset_id）齐备才算 ``is_configured()``。
网络与 API 错误统一抛 :class:`DifyError`，不向上泄漏 requests 异常。
"""

import json

import requests
from django.conf import settings


class DifyError(Exception):
    """Dify 调用失败（网络错误 / 非 2xx / 响应结构不对）。"""

    def __init__(self, message: str, code: str = "", status: int = 0):
        super().__init__(message)
        self.code = code
        self.status = status


def _config() -> dict:
    return settings.DIFY_CONFIG


def is_configured() -> bool:
    cfg = _config()
    return bool(cfg.get("api_base_url") and cfg.get("api_key") and cfg.get("dataset_id"))


def _headers() -> dict:
    return {"Authorization": f"Bearer {_config()['api_key']}"}


def _request(method: str, url: str, **kwargs) -> dict:
    cfg = _config()
    try:
        resp = requests.request(method, url, headers=_headers(), timeout=cfg.get("timeout", 30), **kwargs)
    except requests.RequestException as e:
        raise DifyError(f"Dify 请求失败：{e}") from e
    if resp.status_code >= 400:
        code, message = "", f"Dify 返回 {resp.status_code}"
        try:
            body = resp.json()
            code = str(body.get("code") or "")
            message = str(body.get("message") or message)
        except ValueError:
            pass
        raise DifyError(message, code=code, status=resp.status_code)
    try:
        return resp.json()
    except ValueError as e:
        raise DifyError("Dify 响应不是 JSON") from e


def create_document_by_file(filename: str, content: bytes, content_type: str = "application/octet-stream") -> dict:
    """上传转换产物建文档，返回 ``{"document": {...}, "batch": "..."}``。"""
    cfg = _config()
    if not is_configured():
        raise DifyError("Dify 未配置（DIFY_API_BASE_URL / DIFY_API_KEY / DIFY_DATASET_ID）")
    url = f"{cfg['api_base_url']}/datasets/{cfg['dataset_id']}/document/create-by-file"
    data = {"data": json.dumps(_create_payload(), ensure_ascii=False)}
    files = {"file": (filename, content, content_type)}
    return _request("POST", url, data=data, files=files)


def _create_payload() -> dict:
    cfg = _config()
    return {"indexing_technique": cfg.get("indexing_technique") or "high_quality", "process_rule": {"mode": "automatic"}}


def create_document_by_text(name: str, text: str) -> dict:
    """以文本建文档（md / html 产物走这条），返回 ``{"document": {...}, "batch": "..."}``。"""
    cfg = _config()
    if not is_configured():
        raise DifyError("Dify 未配置（DIFY_API_BASE_URL / DIFY_API_KEY / DIFY_DATASET_ID）")
    url = f"{cfg['api_base_url']}/datasets/{cfg['dataset_id']}/document/create_by_text"
    body = {"name": name, "text": text, **_create_payload()}
    return _request("POST", url, json=body)


def update_document_by_text(document_id: str, name: str, text: str) -> dict:
    """按 document_id 原地更新文档内容（文本），返回 ``{"document": {...}, "batch": "..."}``。"""
    cfg = _config()
    if not is_configured():
        raise DifyError("Dify 未配置（DIFY_API_BASE_URL / DIFY_API_KEY / DIFY_DATASET_ID）")
    url = f"{cfg['api_base_url']}/datasets/{cfg['dataset_id']}/documents/{document_id}/update_by-text"
    body = {"name": name, "text": text}
    return _request("POST", url, json=body)


def update_document_by_file(document_id: str, filename: str, content: bytes, content_type: str = "application/octet-stream") -> dict:
    """按 document_id 原地更新文档内容（文件，pdf 换源文件后走这条）。"""
    cfg = _config()
    if not is_configured():
        raise DifyError("Dify 未配置（DIFY_API_BASE_URL / DIFY_API_KEY / DIFY_DATASET_ID）")
    url = f"{cfg['api_base_url']}/datasets/{cfg['dataset_id']}/documents/{document_id}/update-by-file"
    data = {"data": json.dumps(_create_payload(), ensure_ascii=False)}
    files = {"file": (filename, content, content_type)}
    return _request("POST", url, data=data, files=files)


def indexing_status(batch: str) -> list:
    """查一批文档的索引进度，返回 ``data`` 列表（每项含 id / indexing_status / error）。"""
    cfg = _config()
    if not is_configured():
        raise DifyError("Dify 未配置（DIFY_API_BASE_URL / DIFY_API_KEY / DIFY_DATASET_ID）")
    url = f"{cfg['api_base_url']}/datasets/{cfg['dataset_id']}/documents/{batch}/indexing-status"
    body = _request("GET", url)
    return list(body.get("data") or [])
