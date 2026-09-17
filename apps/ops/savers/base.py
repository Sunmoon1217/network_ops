"""Saver 基类 - 自动注册"""

import ipaddress
from abc import ABC, abstractmethod
from logging import getLogger
from typing import Any

logger = getLogger(__name__)


def as_list(value: Any) -> list:
    """统一成列表。

    TTP 只解析到一条记录时给出的是 dict 而不是 list，直接遍历会拿到 key 字符串，
    导致 saver 里 item.get(...) 抛 AttributeError。
    """
    if not value:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return value
    return []


class BaseSaver(ABC):
    """基类，子类定义 device_types 和 keys 类属性即自动注册"""

    device_types: list[str] = []
    keys: list[str] = []

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.device_types and cls.keys:
            from .registry import _registry

            for dt in cls.device_types:
                for key in cls.keys:
                    _registry[(dt, key)] = cls

    @abstractmethod
    def save(self, device, parsed_data: dict) -> tuple[int, int]:
        """保存数据，返回 (created_count, updated_count)"""

    def _safe_int(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def _safe_ip(self, value: Any) -> str | None:
        """GenericIPAddressField 不接受空串和非法值，统一在这里清洗"""
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return str(ipaddress.ip_address(text))
        except ValueError:
            return None

    def _leaf(self, value: Any) -> str:
        """取 F5 路径名字的末段：``/Common/pool_web`` → ``pool_web``。

        F5 配置里对象名普遍带 ``/Common/`` 分区前缀，而库里的名称字段存末段，
        关联（例如池成员按 server_name 找 GtmServer）也依赖两边写法一致。

        清理放在这里而不是模板里：TTP 的模板函数做不了整串替换——``replaceall``
        是逐字符语义，``re()`` 又只认 ``<vars>`` 里声明的名字、且是"从行里抓取"
        的匹配函数，链在 ``strip('"')`` 之后拿不到标量。
        """
        return str(value or "").strip().strip('"').rstrip("/").rsplit("/", 1)[-1]

    def upsert(self, serializer_cls, model, device, lookup: dict, payload: dict) -> bool:
        """用序列化器 upsert 一条记录，返回是否为新建。

        Saver 调用序列化器的统一入口（序列化器见 ``apps/assets/serializers/views.py``）：

        - ``partial=True``：解析结果只覆盖配置里出现的字段，模型上的必填项不必凑齐。
        - ``device`` 必须放进 payload：带 ``unique_together(device, ...)`` 的模型，DRF 的
          ``UniqueTogetherValidator`` 在 ``instance is None``（create）时会强制要求这些
          字段，仅靠 ``save(device=device)`` 注入过不了校验。
        """
        instance = model.objects.filter(device=device, **lookup).first()
        serializer = serializer_cls(instance, data={**payload, "device": device.pk}, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return instance is None
