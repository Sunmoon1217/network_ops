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
    """根据设备类型和 config_json 获取匹配的 Saver，返回 ``(命中该 Saver 的 key 列表, 实例)``。

    **按 Saver 聚合、不按 key 逐个返回**：一个 Saver 可能注册多个 key（PolicySaver 覆盖
    policies / acl / rules），逐个返回会让调用方只传第一个键，Saver 内部 `a or b or c`
    的短路链把其余键的数据静默丢弃。理由与 payload 规则见 docs/ingest.md
    """
    grouped: dict[type[BaseSaver], list[str]] = {}
    for key in config_json:
        saver_cls = _registry.get((device_type, key))
        if saver_cls:
            grouped.setdefault(saver_cls, []).append(key)
    return [(keys, saver_cls()) for saver_cls, keys in grouped.items()]


def build_saver_payloads(device_type: str, config_json: dict) -> list[tuple[BaseSaver, dict]]:
    """按 Saver 分组，返回 ``(saver 实例, 该 Saver 应该看到的 payload)``。

    **调用方不要自己拼 payload**：同一个 Saver 的多个 key 必须一起传，且只传有值的键。
    这条规则曾散在 pipeline 与两个 Celery 任务里各写一遍，其中一处把 key 列表当单 key
    用而整批存不进去——收敛到这里，别再加第三份。
    """
    payloads: list[tuple[BaseSaver, dict]] = []
    for keys, saver in get_savers_for_config(device_type, config_json):
        payload = {key: config_json[key] for key in keys if config_json.get(key)}
        if payload:
            payloads.append((saver, payload))
    # 被引用的维表先写：Service 的行 pk 稳定后 Policy 才挂 M2M——同批全量解析下
    # PolicySaver._replace_m2m 会按最新 ids 全量重建关联；若反序（Policy 先建关联、
    # Service 后删改端口行），级联删除会打断关联且无人重建。稳定排序，其余相对序不变。
    payloads.sort(key=lambda pair: 0 if type(pair[0]).__name__ == "ServiceSaver" else 1)
    return payloads


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
