"""解析器产出 → Saver → 模型 的关联映射层：把厂商间的键级/字段级差异收敛成声明表。

由 :meth:`ingest.savers.base.BaseSaver.save` 在入口统一归一（键先归一、记录字段再归一），
子类 ``_save`` 只读规范字段。

分层约定（哪些差异该留在 Saver）、为什么声明表不带厂商维度：见 docs/ingest.md
"""

from __future__ import annotations

import importlib
from typing import Any

# 键级归一：原始顶层键 → 规范键。源键必须有真实生产者、目标键必须有 Saver 消费，
# 否则就是死别名——由 tests/ingest/test_mapping.py 守。
KEY_ALIASES: dict[str, str] = {
    # H3C 模板的顶层 group 叫 vpn_instances，模型侧统一叫 vrfs
    "vpn_instances": "vrfs",
    # Cisco 的 acl / Hillstone 的 rules 都是防火墙策略
    "acl": "policies",
    "rules": "policies",
    # Hillstone 的动态组名 addresses.{{ name }} 是地址簿
    "addresses": "address_books",
}

# 字段级归一：规范键 → {原始字段名: 规范字段名}。只做纯改名，值语义转换不进这张表。
FIELD_ALIASES: dict[str, dict[str, str]] = {
    "static_routes": {
        # Maipu / Ruijie：ip route {{ network }} {{ subnet_mask }} {{ next_hop }}
        "subnet_mask": "mask",
    },
    "policies": {
        # Hillstone rules：rule id {{ rule_id }} / name {{ rule_name }}
        "rule_id": "policy_id",
        "rule_name": "name",
        # Cisco acl：access-list {{ acl_name }} extended ...（ACL 名即策略标识；
        # 缺这条时 policy_id 恒为空、整批规则被 PolicySaver 静默跳过）
        "acl_name": "policy_id",
    },
}


def canonical_key(key: str) -> str:
    """原始键 → 规范键；不在别名表里原样返回（幂等）"""
    return KEY_ALIASES.get(key, key)


def canonical_keys(keys: list[str]) -> list[str]:
    """一组原始键 → 去重后的规范键（保持出现顺序）"""
    seen: dict[str, None] = {}
    for key in keys:
        seen.setdefault(canonical_key(key), None)
    return list(seen)


def _as_list(value: Any) -> list:
    """与 Saver 侧 as_list 同语义：dict 单条包成列表，标量也包成列表"""
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return value
    return [value]


def _merge(left: Any, right: Any) -> Any:
    """同一语义键的两份产出按记录拼接（如 config 同时出现 policies 与 acl）。

    拼接而不是字段合并：两份产出是两条独立记录，字段合并会把两条规则揉成一条；
    消费方本就要兼容 dict / list，拉平成列表是安全的。
    """
    if not left:
        return right
    if not right:
        return left
    return _as_list(left) + _as_list(right)


def _rename_fields(value: Any, aliases: dict[str, str]) -> Any:
    """对记录（dict）及其列表做字段改名；非记录形态原样返回"""
    if not aliases:
        return value
    if isinstance(value, dict):
        return {aliases.get(name, name): item for name, item in value.items()}
    if isinstance(value, list):
        return [_rename_fields(item, aliases) for item in value]
    return value


def normalize_config(config_json: dict) -> dict:
    """把一份解析产出归一成规范结构（纯函数，不修改入参）。

    两步：① 顶层键按 :data:`KEY_ALIASES` 归一，同义键合并；
    ② 每个规范键的记录按 :data:`FIELD_ALIASES` 改名字段。

    幂等：对已归一的结构再跑一遍结果不变。调用方是
    ``BaseSaver.save``（原始解析产出进入 Saver 的必经口）。
    """
    if not isinstance(config_json, dict) or not config_json:
        return config_json if isinstance(config_json, dict) else {}

    merged: dict[str, Any] = {}
    for key, value in config_json.items():
        target = canonical_key(key)
        merged[target] = _merge(merged.get(target), value)

    return {key: _rename_fields(value, FIELD_ALIASES.get(key, {})) for key, value in merged.items()}


def resolve_models(model_paths: list[str]) -> list[type]:
    """把 ``["assets.models.Route", ...]`` 解析成模型类列表（供接口与契约测试）。

    用点路径字符串而不是在类体里直接引用模型：``savers`` 模块的 import 时机
    早于 Django app registry 就绪是不可控的（模型侧也因此都在函数内 import），
    字符串把解析推迟到真正需要时。
    """
    models: list[type] = []
    for path in model_paths:
        module_name, _, attr = path.rpartition(".")
        if not module_name:
            raise ValueError(f"模型路径格式应为 'app.models.Class': {path}")
        module = importlib.import_module(module_name)
        models.append(getattr(module, attr))
    return models
