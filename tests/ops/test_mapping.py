"""映射层（``ops.mapping``）的行为与声明契约。

对应关系：解析器按 (vendor, device_type) 注册、产出**原始**键与字段；Saver 按
(device_type, key) 注册（key 含别名）并声明写入的模型；``ops.mapping`` 的两张
声明表把不同厂商的同语义键 / 字段归一到规范名（由 ``BaseSaver.save`` 执行）。

这里守两件事：

1. 归一行为本身：键合并、字段改名、幂等、不改入参；
2. 声明表不能说谎：别名的源键必须真有解析器产出、目标键必须真有 Saver 消费、
   Saver 声明的模型必须真实存在且属于 ``ConfigBase``。
"""

import pytest

from assets.models import ConfigBase
from ops.mapping import (
    FIELD_ALIASES,
    KEY_ALIASES,
    canonical_key,
    normalize_config,
    resolve_models,
)
from ops.parsers.factory import ParserFactory
from ops.savers.registry import all_savers


def _all_produced_keys() -> set[str]:
    keys: set[str] = set()
    for parser_cls in ParserFactory._registry.values():
        keys.update(parser_cls.provides_keys)
    return keys


# ---------- 归一行为 ----------


def test_key_alias_normalized_to_canonical():
    config = {"vpn_instances": [{"vrf": "VPN-A", "rd": "100:1"}]}
    assert normalize_config(config) == {"vrfs": [{"vrf": "VPN-A", "rd": "100:1"}]}


def test_alias_keys_of_same_saver_are_merged():
    """policies + acl 同时出现时按记录拼接，不丢任何一条"""
    config = {"policies": [{"policy_id": "1"}], "acl": [{"acl_name": "2"}]}
    normalized = normalize_config(config)

    assert list(normalized) == ["policies"]
    assert normalized["policies"] == [{"policy_id": "1"}, {"policy_id": "2"}]


def test_single_dict_alias_records_stay_separate():
    """TTP 单条命中（dict）的两个别名键是**两条记录**，不能字段揉成一条"""
    config = {"acl": {"acl_name": "a"}, "rules": {"rule_id": "b"}}
    normalized = normalize_config(config)

    assert normalized["policies"] == [{"policy_id": "a"}, {"policy_id": "b"}]


def test_static_route_field_alias_renamed():
    config = {"static_routes": [{"destination_network": "10.0.0.0", "subnet_mask": "255.255.0.0"}]}
    (record,) = normalize_config(config)["static_routes"]

    assert record["mask"] == "255.255.0.0"
    assert "subnet_mask" not in record


def test_hillstone_rule_fields_renamed_to_policy_fields():
    config = {"rules": [{"rule_id": "9", "rule_name": "web", "action": "permit"}]}
    (record,) = normalize_config(config)["policies"]

    assert record["policy_id"] == "9"
    assert record["name"] == "web"
    # 值语义字段（action 用词）不改名，转换留给 Saver
    assert record["action"] == "permit"


def test_normalize_is_idempotent_and_pure():
    config = {"rules": [{"rule_id": "9"}], "static_routes": [{"subnet_mask": "255.255.0.0"}]}
    snapshot = {"rules": [{"rule_id": "9"}], "static_routes": [{"subnet_mask": "255.255.0.0"}]}
    once = normalize_config(config)

    assert config == snapshot, "normalize_config 不得修改入参"
    assert normalize_config(once) == once, "归一必须幂等"


def test_unaliased_keys_pass_through():
    """没有别名声明的键 / 字段原样通过（含字典型值的 address_books 形态）"""
    config = {
        "vlans": [{"vlan_id": "10"}],
        "hostname": "sw1",
        "address_books": {"office": {"ip": ["10.0.0.0/24"]}},
    }
    assert normalize_config(config) == config


def test_canonical_key_is_idempotent():
    for source, target in KEY_ALIASES.items():
        assert canonical_key(source) == target
        assert canonical_key(target) == target


# ---------- 声明契约 ----------


def test_key_alias_source_has_producer():
    """别名的源键必须真有解析器产出（否则是死别名）"""
    produced = _all_produced_keys()
    dead = [source for source in KEY_ALIASES if source not in produced]
    assert not dead, f"KEY_ALIASES 里没有解析器产出的死别名: {dead}"


def test_key_alias_target_consumed_by_saver():
    """别名的规范键必须有 Saver 注册（否则归一后无人消费）"""
    registered = {key for _device_type, key in all_savers()}
    orphan = [target for target in set(KEY_ALIASES.values()) if target not in registered]
    assert not orphan, f"归一后无人消费的键: {orphan}"


def test_field_alias_keys_are_canonical_and_consumed():
    """FIELD_ALIASES 必须按规范键索引，且该键有 Saver 消费"""
    registered = {key for _device_type, key in all_savers()}
    bad = []
    for key in FIELD_ALIASES:
        if canonical_key(key) != key:
            bad.append(f"{key} 不是规范键（别名键应先过 KEY_ALIASES）")
        if key not in registered:
            bad.append(f"{key} 无任何 Saver 注册，字段归一永远不生效")
    assert not bad, "\n".join(bad)


def test_every_registered_saver_declares_models():
    """每个 Saver 必须声明写入的模型，且模型真实存在、属于配置基类"""
    bad: list[str] = []
    seen: set[type] = set()
    for (_device_type, _key), saver_cls in all_savers().items():
        if saver_cls in seen:
            continue
        seen.add(saver_cls)
        if not saver_cls.model_paths:
            bad.append(f"{saver_cls.__name__} 未声明 model_paths")
            continue
        for model in resolve_models(saver_cls.model_paths):
            if not issubclass(model, ConfigBase):
                bad.append(f"{saver_cls.__name__} 的 {model.__name__} 不是 ConfigBase 子类")
    assert not bad, "\n".join(sorted(set(bad)))


def test_resolve_models_rejects_bad_path():
    with pytest.raises(ValueError, match="app.models.Class"):
        resolve_models(["NoDotPath"])
