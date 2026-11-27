"""端口 / Service 协议端口的纯工具归一。

"范围结束端口非空且与起始不同才算范围"这条规则散落在至少四处：
policy_expand.service_parts 的十元组归一、
path_tracer._match_service 的范围拼接、
assets.serializers._format_service_entry 的展示串、
configs.models.Service admin 列表的 label。
统一到一个入口省得四处维护。
"""

from __future__ import annotations

from typing import Any


def _canon_port(value: Any) -> str:
    """单个端口值归一：strip + 纯数字去前导零（空值归空串）。"""
    text = str(value or "").strip()
    if not text:
        return ""
    # str(int("080")) → "80"；非纯数字（命名端口）原样保留
    return str(int(text)) if text.isdigit() else text


def normalize_port(port: Any, port2: Any) -> tuple[str, str]:
    """Service 起止端口 → 归一化 ``(start, end)`` 二元组。

    规则：两者都过 ``_canon_port``，且当 ``end == start`` 时 end 归空串——
    和 AccessFlow 模型的 ``port2`` 字段语义（空串=非范围）完全一致。
    """
    start = _canon_port(port)
    end = _canon_port(port2)
    if end == start:
        end = ""
    return start, end


def service_label(protocol: Any, port: Any, port2: Any) -> str:
    """Service 的可读展示串：``协议/端口``（范围时是 ``协议/起-止``）。

    与 ``assets.serializers._format_service_entry`` 原逻辑一致：
    protocol 只做 strip + lower，不做额外归一（调用方若要 "any" 需自己传）。
    """
    proto = str(protocol or "").strip().lower()
    start, end = normalize_port(port, port2)

    if start and end:
        port_str = f"{start}-{end}"
    else:
        port_str = start or end

    if port_str and proto:
        return f"{proto}/{port_str}"
    return port_str or proto


__all__ = ["normalize_port", "service_label"]
