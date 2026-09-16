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


def get_savers_for_config(device_type: str, config_json: dict) -> list[tuple[str, BaseSaver]]:
    """根据设备类型和 config_json 获取匹配的 Saver"""
    result = []
    seen = set()
    for key in config_json:
        saver_cls = _registry.get((device_type, key))
        if saver_cls and saver_cls not in seen:
            seen.add(saver_cls)
            result.append((key, saver_cls()))
    return result


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
