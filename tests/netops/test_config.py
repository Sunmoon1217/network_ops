"""``netops.config``：结构化配置的读取、严格校验与路径解析。"""

import json
from pathlib import Path

import pytest
from django.conf import settings

from netops.config import ConfigError, StrictModel, load_json_config, resolve_config_path


class _Demo(StrictModel):
    name: str
    count: int


def _write(tmp_path: Path, data) -> Path:
    path = tmp_path / "demo.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_loads_valid_json(tmp_path):
    config = load_json_config(_write(tmp_path, {"name": "x", "count": 1}), _Demo)

    assert config.name == "x"
    assert config.count == 1


def test_rejects_unknown_field(tmp_path):
    """拼错的字段必须报错，不能被静默忽略。"""
    with pytest.raises(ConfigError, match="字段校验失败"):
        load_json_config(_write(tmp_path, {"name": "x", "count": 1, "extra": True}), _Demo)


def test_rejects_wrong_type_strictly(tmp_path):
    with pytest.raises(ConfigError, match="count"):
        load_json_config(_write(tmp_path, {"name": "x", "count": "1"}), _Demo)


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="不可读"):
        load_json_config(tmp_path / "missing.json", _Demo)


def test_bad_json(tmp_path):
    path = tmp_path / "demo.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(ConfigError, match="JSON"):
        load_json_config(path, _Demo)


def test_relative_path_resolves_against_base_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)
    (tmp_path / "conf").mkdir()
    (tmp_path / "conf" / "demo.json").write_text(json.dumps({"name": "x", "count": 1}), encoding="utf-8")

    assert resolve_config_path("conf/demo.json") == tmp_path / "conf" / "demo.json"
    assert load_json_config("conf/demo.json", _Demo).name == "x"
