"""解析器产出 → Saver → 模型 的关联映射层。

不同厂商 / 类型的解析器解析出的**同一语义关键字**，内部结构并不一致：

- **键级差异**：H3C 产出 ``vpn_instances``、Cisco 产出 ``acl``、Hillstone 产出
  ``rules`` / ``addresses``——语义上分别是 vrfs / policies / address_books。
- **字段级差异**：Maipu / Ruijie 的静态路由用 ``subnet_mask``，其余厂商用 ``mask``；
  Hillstone 规则的 ``rule_id`` / ``rule_name``、Cisco ACL 的 ``acl_name``
  对不上 PolicySaver 期望的 ``policy_id`` / ``name``。

本模块把这两类差异收敛成**声明式字典**，由 :meth:`ingest.savers.base.BaseSaver.save`
在入口统一归一（键先归一、记录字段再归一），子类 ``_save`` 只读规范字段——
即「相同关键字的不同内部接口，经 Saver 归一后映射到统一模型」。

分层约定（越界即混层）：

1. **键级 / 字段级结构归一** → 本模块的声明表；
2. **值语义转换**（permit→allow、enable/disable→bool、route→layer3）→ 留在
   Saver 内部——那是业务规则，不是结构改名，混进声明表会被误读成"字段同义"；
3. **结构级差异**（SNMP 的 community / target_hosts 两种形态、Hillstone 扁平
   地址拆 AddressBook）→ 留在 Saver——需要遍历 / 拼接，声明表表达不了。

声明表**不带厂商维度**：同一规范键下的字段同义性是"键的字段字典"级别的事实
（``static_routes`` 下 ``subnet_mask`` 恒等于 ``mask``，无论谁产出），按厂商拆
反而会让无型号的 device（测试里常见）归一失败。未来若真出现"同名字段在不同
厂商下含义不同"，再给 :data:`FIELD_ALIASES` 加厂商维度。
"""

from __future__ import annotations

import importlib
from typing import Any

# ---------------------------------------------------------------------------
# 键级归一：解析器产出的原始顶层键 → 规范键（Saver / 模型侧的统一关键字）
# ---------------------------------------------------------------------------
# 源键必须有真实生产者（模板顶层 group），目标键必须有 Saver 消费，
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

# ---------------------------------------------------------------------------
# 字段级归一：规范键 → {原始字段名: 规范字段名}
# ---------------------------------------------------------------------------
# 规范字段 = 模型 / Saver 侧的统一字段名（多数模板的产出形态）。
# 只做**纯改名**：值语义转换不进这张表（见模块 docstring 的分层约定）。
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
    """同一语义键的两份产出按**记录拼接**（如 config 同时出现 policies 与 acl）。

    拼接而不是字段合并：别名键的两份产出是**两条独立记录**（TTP 单条命中给
    dict，若 dict 与 dict 合并字段会把两条规则揉成一条）。消费方（Saver）
    本就要兼容 dict / list 两种形态，拉平成列表是安全的。
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


# ---------------------------------------------------------------------------
# Saver → 模型 关联
# ---------------------------------------------------------------------------


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
