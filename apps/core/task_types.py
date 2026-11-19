"""业务词汇注册表：任务类型、阶段类型与作用目标的登记与反查。

词汇由业务域在 ``AppConfig.ready()`` 里注册（方向：域 → core），本模块只维护纯 dict，
且**不在顶层 import 任何模型**（``ready()`` 阶段 app registry 尚未就绪）。
约束与取舍见 ``handbook/tasks.md``。
"""

from __future__ import annotations

import logging
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)


class _TaskType(NamedTuple):
    """任务类型：显示名 + 首个阶段 + 是否允许用户手工创建。"""

    label: str
    first_stage: str
    #: 能否由用户在任务页 / API 手工创建（导入这类内部任务只能由业务代码投递）
    creatable: bool = True


class _Stage(NamedTuple):
    """阶段类型：显示名 + 执行它的 celery 任务对象。"""

    label: str
    handler: Any


class _TargetType(NamedTuple):
    """作用目标类型：显示名 + ``target_id`` → 显示名的 resolver。"""

    label: str
    #: ``target_id -> 显示名``；目标不存在时返回 ``None``（core 靠它校验 device 参数）
    resolver: Any


# 词汇表：{task_type: _TaskType} / {stage_type: _Stage} / {target_type: _TargetType}
_TASK_TYPES: dict[str, _TaskType] = {}
_STAGES: dict[str, _Stage] = {}
_TARGET_TYPES: dict[str, _TargetType] = {}
#: 填 ``Task.device`` / ``Task.device_hostname`` 两个历史字段的那个 target_type
_DEVICE_TARGET_TYPE = ""


def register_task_type(task_type: str, label: str, first_stage: str, *, creatable: bool = True) -> None:
    """登记一个任务类型及其第一个阶段；重复登记覆盖旧值。"""
    if not task_type:
        raise ValueError("task_type 不能为空")
    previous = _TASK_TYPES.get(task_type)
    if previous and previous != _TaskType(label, first_stage, creatable):
        logger.debug("任务类型 %s 被重新登记：%s → %s", task_type, previous, (label, first_stage, creatable))
    _TASK_TYPES[task_type] = _TaskType(label=label, first_stage=first_stage, creatable=creatable)


def register_stage(stage_type: str, label: str, handler: Any) -> None:
    """登记一个阶段：显示名 + 执行它的 celery 任务对象（必须有 ``.delay()``）。"""
    if not stage_type:
        raise ValueError("stage_type 不能为空")
    if not hasattr(handler, "delay"):
        raise TypeError(f"阶段 {stage_type} 的 handler 必须是 celery 任务（缺 .delay）: {handler!r}")
    _STAGES[stage_type] = _Stage(label=label, handler=handler)


def register_target_type(target_type: str, label: str, resolver: Any, *, feeds_device_fields: bool = False) -> None:
    """登记一种任务作用目标及 ``resolver(target_id) -> str | None``。

    resolver 在目标不存在时必须返回 ``None``——这是「目标不成立」的唯一信号。
    ``feeds_device_fields=True`` 的类型会填 ``Task.device`` / ``device_hostname``（只应有一个）。
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
    """按 task_type 或 stage_type 反查显示名（两张表分开查），查不到回落原字符串。"""
    for table in (_TASK_TYPES, _STAGES):
        entry = table.get(kind)
        if entry is not None:
            return entry.label
    return kind


def first_stage_of(task_type: str) -> str:
    """任务类型的第一个阶段。未登记的类型是**调用方写错了**，显式抛 ``LookupError``。"""
    try:
        return _TASK_TYPES[task_type].first_stage
    except KeyError:
        registered = sorted(_TASK_TYPES)
        raise LookupError(f"未知的任务类型 {task_type!r}，已登记：{registered}") from None


def handler_for(stage_type: str) -> Any:
    """按 stage_type 取执行它的 celery 任务对象；未登记抛 ``LookupError``。"""
    try:
        return _STAGES[stage_type].handler
    except KeyError:
        registered = sorted(_STAGES)
        raise LookupError(f"未知的阶段类型 {stage_type!r}，已登记：{registered}") from None


def is_registered_task_type(task_type: str) -> bool:
    """该任务类型是否已登记（API 层校验用）。"""
    return task_type in _TASK_TYPES


def is_creatable_task_type(task_type: str) -> bool:
    """该任务类型能否由用户手工创建；未登记或标记为不可建都返回 ``False``。"""
    entry = _TASK_TYPES.get(task_type)
    return bool(entry and entry.creatable)


def task_type_choices() -> list[tuple[str, str]]:
    """运行期快照，喂给 DRF ``ChoiceField`` 或 admin ``list_filter``（不进迁移）。"""
    return [(key, entry.label) for key, entry in _TASK_TYPES.items()]


def stage_type_choices() -> list[tuple[str, str]]:
    """阶段类型的运行期快照（同 ``task_type_choices``）。"""
    return [(key, entry.label) for key, entry in _STAGES.items()]


def target_type_choices() -> list[tuple[str, str]]:
    """作用目标类型的运行期快照（同 ``task_type_choices``）。"""
    return [(key, entry.label) for key, entry in _TARGET_TYPES.items()]


def target_label_for(target_type: str) -> str:
    """作用目标类型的显示名（未登记回落 key）。"""
    entry = _TARGET_TYPES.get(target_type)
    return entry.label if entry else target_type


def resolve_target_label(target_type: str, target_id: int) -> str | None:
    """把作用目标的主键解析成显示名；类型未登记或目标不存在都返回 ``None``。"""
    entry = _TARGET_TYPES.get(target_type)
    if entry is None:
        return None
    return entry.resolver(target_id)


def device_field_target_type() -> str:
    """填 ``Task.device`` / ``Task.device_hostname`` 的 target_type（未登记为 ``""``）。"""
    return _DEVICE_TARGET_TYPE
