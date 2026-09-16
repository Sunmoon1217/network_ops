"""Saver 注册表 - 基于 __init_subclass__ 自动注册"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import BaseSaver

logger = logging.getLogger(__name__)

_registry: dict[tuple[str, str], type[BaseSaver]] = {}


def all_savers() -> dict[tuple[str, str], type[BaseSaver]]:
    """返回注册表快照，供映射清单接口与契约测试使用"""
    return dict(_registry)


def get_savers_for_config(device_type: str, config_json: dict) -> list[tuple[list[str], BaseSaver]]:
    """根据设备类型和 config_json 获取匹配的 Saver。

    一个 Saver 可能注册了多个 key（例如 PolicySaver 覆盖 policies / acl / rules）。
    这里把命中**同一个 Saver** 的 key 聚合后一并交给它——若按 key 逐个返回，
    调用方只能把第一个键的数据传进去，Saver 内部 `a or b or c` 的短路链
    会让其余键的数据被静默丢弃。
    """
    grouped: dict[type[BaseSaver], list[str]] = {}
    for key in config_json:
        saver_cls = _registry.get((device_type, key))
        if saver_cls:
            grouped.setdefault(saver_cls, []).append(key)
    return [(keys, saver_cls()) for saver_cls, keys in grouped.items()]


def register(device_types: list[str], keys: list[str]):
    """类装饰器：注册 Saver 到指定设备类型和 key

    Usage::

        @register(device_types=["switch", "router"], keys=["interfaces"])
        class InterfaceSaver(BaseSaver):
            ...
    """

    def decorator(cls):
        for dt in device_types:
            for key in keys:
                _registry[(dt, key)] = cls
        return cls

    return decorator
