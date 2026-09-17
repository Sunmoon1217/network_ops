"""Saver 基类 - 自动注册"""

import ipaddress
from abc import ABC, abstractmethod
from logging import getLogger
from typing import Any

from django.utils import timezone

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

    def _leaf_list(self, value: Any) -> list[str]:
        """对名字列表逐个取末段；单值也接受。"""
        items = [value] if isinstance(value, str) else as_list(value)
        return [self._leaf(item) for item in items if item]

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

    def bulk_upsert(
        self,
        model,
        device,
        rows: list[dict],
        *,
        key_fields: tuple[str, ...],
        serializer_cls=None,
    ) -> tuple[int, int]:
        """批量 upsert，返回 ``(新建数, 更新数)``。

        与 ``upsert`` 语义一致：按 ``key_fields`` 定位现有行、只覆盖 payload 里出现的
        字段。区别在于把「每行一次 SELECT + 一次 INSERT/UPDATE」压成「一次 SELECT +
        一次 bulk_create / 一次 bulk_update」。

        为什么值得这么做：本机的 Postgres 跑在容器里、经宿主机端口映射，**每跳往返
        约 0.95 ms**，所以语句条数就是主要成本——逐行写时一次导入能发出上万条 SQL。
        实测 PolicySaver 平均 19.8 条 SQL/行、LBPoolSaver 10 条/行。

        ``serializer_cls`` 给了就逐行走它校验，**保持 views 与 savers 共用同一套字段
        规则**；不给就直接落库（原本就用原生 ORM 的 Saver）。

        不支持 M2M 字段：带 M2M 的模型（``Policy`` / ``NatRule``）的关联表要调用方
        自己处理，别把 M2M 的值塞进 ``rows``。
        """
        if not rows:
            return (0, 0)

        def key_of(row: dict) -> tuple:
            """取行的键。

            用 ``.get``：可空的键字段（例如只在 range 类型上才有的 ``ip_start``）
            缺失即 ``None``，与 ``existing`` 那边 ``getattr`` 拿到 ``None`` 对齐。
            """
            return tuple(row.get(field) for field in key_fields)

        # 同一批里出现相同的键：按顺序后来者覆盖（与逐条 upsert 的语义一致）。
        # 不去重的话两条都会进 bulk_create，直接撞唯一约束。
        deduped: dict[tuple, dict] = {}
        for row in rows:
            deduped[key_of(row)] = row
        rows = list(deduped.values())

        existing = {
            tuple(getattr(obj, field) for field in key_fields): obj for obj in model.objects.filter(device=device)
        }

        to_create: list = []
        to_update: list = []
        update_fields: set[str] = set()

        for row in rows:
            key = key_of(row)
            instance = existing.get(key)
            payload = dict(row)

            if serializer_cls is not None:
                serializer = serializer_cls(instance, data={**payload, "device": device.pk}, partial=True)
                serializer.is_valid(raise_exception=True)
                payload = dict(serializer.validated_data)

            # device 由 Saver 统一指定（与 upsert 一致），payload 里若也带了就丢掉，
            # 否则 model(device=device, **payload) 会重复传参
            payload.pop("device", None)

            if instance is None:
                to_create.append(model(device=device, **payload))
            else:
                for field, value in payload.items():
                    if field in key_fields:
                        continue
                    setattr(instance, field, value)
                    update_fields.add(field)
                to_update.append(instance)

        if to_create:
            model.objects.bulk_create(to_create, batch_size=500)
        if to_update:
            # bulk_update 不走 pre_save，auto_now 的 updated_at 得自己填
            if hasattr(model, "updated_at"):
                now = timezone.now()
                for obj in to_update:
                    obj.updated_at = now
                update_fields.add("updated_at")
            model.objects.bulk_update(to_update, sorted(update_fields), batch_size=500)

        return (len(to_create), len(to_update))
