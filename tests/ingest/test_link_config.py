"""链路带宽配置（``conf/links.json``）的读取、校验与脱敏投影。"""

import json
from pathlib import Path

import pytest
from django.conf import settings

from ingest.collectors.link_config import (
    CONFIG_VERSION,
    LinkConfigError,
    config_path,
    load_links_config,
    parse_links_config,
)

REPO_CONFIG = Path(settings.BASE_DIR) / "conf" / "links.json"


def _valid() -> dict:
    return {
        "version": CONFIG_VERSION,
        "panels": [{"id": "internet", "label": "互联网链路使用率", "scopes": ["ipv4"]}],
        "scopes": {"ipv4": "IPv4 互联网链路"},
        "targets": [
            {"scope": "ipv4", "subject": "zjbgp", "label": "中金BGP", "host": "h1", "ifname": "eth0"},
            {"scope": "ipv4", "subject": "jxqcu", "label": "世纪互联联通", "host": "h2", "ifname": "eth1", "enabled": False},
        ],
    }


def test_repo_config_is_valid():
    config = load_links_config(REPO_CONFIG)
    assert {panel.id for panel in config.panels} == {"internet", "firewall"}
    assert len(config.targets) == 10
    assert len(config.enabled_targets()) == 10


def test_meta_hides_host_and_ifname():
    config = parse_links_config(_valid())
    meta = config.meta()
    assert meta["panels"] == [{"id": "internet", "label": "互联网链路使用率", "scopes": ["ipv4"]}]
    assert meta["targets"][0] == {"scope": "ipv4", "subject": "zjbgp", "label": "中金BGP", "enabled": True}
    assert "host" not in meta["targets"][0]
    assert "ifname" not in meta["targets"][0]


def test_enabled_targets_filters_disabled():
    config = parse_links_config(_valid())
    assert [target.subject for target in config.enabled_targets()] == ["zjbgp"]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda data: data.update(version=2), "version"),
        (lambda data: data.update(scopes={}), "scopes"),
        (lambda data: data["panels"][0].update(scopes=["unknown"]), "未定义的 scope"),
        (lambda data: data["targets"][0].update(scope="unknown"), "未在 scopes 中定义"),
        (lambda data: data["targets"][1].update(subject="zjbgp"), "重复"),
        (lambda data: data["targets"][0].update(label=""), "label"),
        (lambda data: data["targets"][0].update(enabled="yes"), "enabled"),
    ],
)
def test_invalid_config_is_rejected(mutate, message):
    data = _valid()
    mutate(data)
    with pytest.raises(LinkConfigError, match=message):
        parse_links_config(data)


def test_missing_file(tmp_path):
    with pytest.raises(LinkConfigError, match="不可读"):
        load_links_config(tmp_path / "missing.json")


def test_bad_json(tmp_path):
    path = tmp_path / "links.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(LinkConfigError, match="JSON"):
        load_links_config(path)


def test_config_path_resolves_relative_to_base_dir(monkeypatch):
    monkeypatch.setenv("DASHBOARD_LINKS_FILE", "conf/links.json")
    assert config_path() == Path(settings.BASE_DIR) / "conf" / "links.json"

    monkeypatch.setenv("DASHBOARD_LINKS_FILE", "/etc/netops/conf/links.json")
    assert config_path() == Path("/etc/netops/conf/links.json")


def test_repo_config_lists_ten_targets_with_labels():
    config = load_links_config(REPO_CONFIG)
    labels = {target.label for target in config.targets}
    assert {"中金BGP", "世纪互联联通", "核心业务区", "互联网DMZ"} <= labels
    assert json.dumps(config.meta(), ensure_ascii=False)
