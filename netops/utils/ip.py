"""IP 地址的纯工具归一：验证 / 规范化 / 兜底策略分派。

项目里散落了 ``ipaddress.ip_address(x)`` 的 ``try/except`` 至少 5 处，
且非法值的兜底策略各不同（返回 None / 返回 lower / 抛异常）。
这里按语义拆成三个入口，调用方挑自己要的。
"""

from __future__ import annotations

import ipaddress
from typing import Any


def is_valid_ip(value: Any) -> bool:
    """字符串是否为合法的 IPv4 / IPv6 地址。"""
    try:
        ipaddress.ip_address(str(value or "").strip())
        return True
    except (ValueError, TypeError):
        return False


def canon_ip_or_none(value: Any) -> str | None:
    """IP 规范化：合法地址返回 canonical form，非法或空返回 None。

    返回值可直接喂给 GenericIPAddressField（它要求 ``None`` 而不是 ``""``）。
    被 ``configs.savers.base.BaseSaver._safe_ip`` 与
    ``analysis.policy_expand._canon_ip`` 两处使用的语义。
    """
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        return None


def canon_ip_or_lower(value: Any) -> str:
    """IP 规范化：合法地址返回 canonical form，非法值原样 lower() 后返回。

    用于"归一化后再做字符串匹配"的场景——如访问流去重（IPv6 大小写/压缩写法统一），
    非法值不应被静默丢弃，而是保留 lower() 形态供上层继续判断。
    """
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        return text.lower()


__all__ = ["is_valid_ip", "canon_ip_or_none", "canon_ip_or_lower"]
