"""业务词汇注册表：任务类型、阶段类型的词汇与显示名，以及作用目标的解析。

为什么要有这张表（见 ``handbook/tasks.md``）：

- ``core`` 只提供「建任务 / 投递阶段 / 取消」这套**通用机制**，它不该认识
  ``collect_config`` / ``collection`` 这类业务词汇——那些是各业务域的语义。
- 于是词汇由业务域在 ``AppConfig.ready()`` 里**主动注册进来**（方向永远是
  业务域 → core，core 不反向 import 任何域），core 只在需要时按 key 反查。

作用目标（``target_type`` / ``target_id``）也在这里登记：``Task`` 用软引用指向任意业务
实体，core 不知道「设备」是什么，只在需要校验、需要显示名时调业务域给出的 resolver。

两条硬约束：

1. **本模块不得在顶层 import 任何模型**。它会被业务域的 ``ready()`` 触发，那一刻
   app registry 还没就绪，import 模型会 ``AppRegistryNotReady``。这里只维护纯 dict。
2. **handler 只在本进程内解析**。Celery 消息必须可序列化，函数对象过不了 Redis，
   所以 handler 由投递方进程从注册表取出后 ``.delay()``，不会跨 broker 传递。

为什么不把词汇写成模型字段的 ``choices`` 再运行时往里追加：``choices`` 是类属性，
``makemigrations`` 会持续对漂移生成迁移，运行时注册会让迁移状态与代码状态永远对不上。
所以词汇表在这里，模型的 ``task_type`` / ``stage_type`` 是自由字符串。
"""

from __future__ import annotations

import logging
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)


class _TaskType(NamedTuple):
    label: str
    first_stage: str


class _Stage(NamedTuple):
    label: str
    handler: Any


class _TargetType(NamedTuple):
    label: str
    #: ``target_id -> 显示名``；目标不存在时返回 ``None``（core 靠它校验 device 参数）
    resolver: Any


# 词汇表：{task_type: _TaskType} / {stage_type: _Stage} / {target_type: _TargetType}
_TASK_TYPES: dict[str, _TaskType] = {}
_STAGES: dict[str, _Stage] = {}
_TARGET_TYPES: dict[str, _TargetType] = {}
#: 填 ``Task.device`` / ``Task.device_hostname`` 两个历史字段的那个 target_type
_DEVICE_TARGET_TYPE = ""


def register_task_type(task_type: str, label: str, first_stage: str) -> None:
    """登记一个任务类型及其**第一个**阶段。

    ``first_stage`` 让 core 在建任务时不必硬编码「先跑 collection」——那是业务知识。
    重复登记覆盖旧值：``ready()`` 在测试里可能被触发多次，允许幂等重放。
    """
    if not task_type:
        raise ValueError("task_type 不能为空")
    previous = _TASK_TYPES.get(task_type)
    if previous and previous != _TaskType(label, first_stage):
        logger.debug("任务类型 %s 被重新登记：%s → %s", task_type, previous, (label, first_stage))
    _TASK_TYPES[task_type] = _TaskType(label=label, first_stage=first_stage)


def register_stage(stage_type: str, label: str, handler: Any) -> None:
    """登记一个阶段：显示名 + 执行它的 celery 任务对象（必须有 ``.delay()``）。"""
    if not stage_type:
        raise ValueError("stage_type 不能为空")
    if not hasattr(handler, "delay"):
        raise TypeError(f"阶段 {stage_type} 的 handler 必须是 celery 任务（缺 .delay）: {handler!r}")
    _STAGES[stage_type] = _Stage(label=label, handler=handler)


def register_target_type(target_type: str, label: str, resolver: Any, *, feeds_device_fields: bool = False) -> None:
    """登记一种「任务作用目标」及把目标主键解析成名字的函数。

    ``resolver(target_id) -> str | None``：目标存在返回它的显示名（设备名、组名…），
    不存在返回 ``None``。core 靠它校验客户端传来的 ``device`` 是否真的存在——
    这就是「软引用」下补回外键校验能力的办法，而且 core 自己不查任何业务表。

    ``feeds_device_fields=True`` 的那个类型会填 ``Task.device`` / ``Task.device_hostname``
    两个历史字段（前端契约还没换）；同时只应有一个类型声明它。
    """
    if not target_type:
        raise ValueError("target_type 不能为空")
    if not callable(resolver):
        raise TypeError(f"作用目标 {target_type} 的 resolver 必须可调用: {resolver!r}")
    global _DEVICE_TARGET_TYPE
    _TARGET_TYPES[target_type] = _TargetType(label=label, resolver=resolver)
    if feeds_device_fields:
        _DEVICE_TARGET_TYPE = target_type


def reset() -> None:
    """清空注册表。**仅供测试**用，业务代码不要调。"""
    global _DEVICE_TARGET_TYPE
    _TASK_TYPES.clear()
    _STAGES.clear()
    _TARGET_TYPES.clear()
    _DEVICE_TARGET_TYPE = ""


def label_for(kind: str) -> str:
    """按 task_type 或 stage_type 反查显示名。

    两表分开查是有意的：``task_type`` 与 ``stage_type`` 命名空间互不相干
    （将来两边出现同名 key 也不该串）。查不到时回落原字符串——
    前端展示比抛异常更重要，未知词汇的 display 至少能看到 key。
    """
    for table in (_TASK_TYPES, _STAGES):
        entry = table.get(kind)
        if entry is not None:
            return entry.label
    return kind


def first_stage_of(task_type: str) -> str:
    """任务类型的第一个阶段。未登记的类型是**调用方写错了**，必须显式失败。"""
    try:
        return _TASK_TYPES[task_type].first_stage
    except KeyError:
        registered = sorted(_TASK_TYPES)
        raise LookupError(f"未知的任务类型 {task_type!r}，已登记：{registered}") from None


def handler_for(stage_type: str) -> Any:
    """按 stage_type 取执行它的 celery 任务对象。"""
    try:
        return _STAGES[stage_type].handler
    except KeyError:
        registered = sorted(_STAGES)
        raise LookupError(f"未知的阶段类型 {stage_type!r}，已登记：{registered}") from None


def is_registered_task_type(task_type: str) -> bool:
    return task_type in _TASK_TYPES


def task_type_choices() -> list[tuple[str, str]]:
    """运行期快照，喂给 DRF ``ChoiceField`` 或 admin ``list_filter``（不进迁移）。"""
    return [(key, entry.label) for key, entry in _TASK_TYPES.items()]


def stage_type_choices() -> list[tuple[str, str]]:
    return [(key, entry.label) for key, entry in _STAGES.items()]


def target_type_choices() -> list[tuple[str, str]]:
    return [(key, entry.label) for key, entry in _TARGET_TYPES.items()]


def target_label_for(target_type: str) -> str:
    """作用目标类型的显示名（未登记回落 key）。"""
    entry = _TARGET_TYPES.get(target_type)
    return entry.label if entry else target_type


def resolve_target_label(target_type: str, target_id: int) -> str | None:
    """把作用目标的主键解析成显示名；类型未登记或目标不存在都返回 ``None``。

    ``None`` 是「这个目标不成立」的唯一信号：API 层据此把非法 device 拒成 400，
    建任务时据此顺带把名字记进 ``Task.target_label``（列表展示不再回查业务表）。
    """
    entry = _TARGET_TYPES.get(target_type)
    if entry is None:
        return None
    return entry.resolver(target_id)


def device_field_target_type() -> str:
    """填 ``Task.device`` / ``Task.device_hostname`` 的 target_type（未登记为 ``""``）。

    core 因此不用硬编码 ``"device"`` 这个词：谁声明了 ``feeds_device_fields``，
    谁就是这个历史契约的提供方。
    """
    return _DEVICE_TARGET_TYPE
