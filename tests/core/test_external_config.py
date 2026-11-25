"""外部连接配置的统一 schema：``base_url`` / ``credential_ref`` / ``timeout`` / ``enabled``。

四套配置（Zabbix / 阿里云 / Dify / autotask）字段同名同义，消费方一律看 ``enabled``，
不再各自判断 url / api_key / AK 是否存在——这是 ``design/external-clients.md`` Step 1 的契约。
"""

import asyncio

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

CONFIG_NAMES = ("ZABBIX_CONFIG", "ALIYUN_CONFIG", "DIFY_CONFIG", "AUTOTASK_CONFIG")


def test_all_external_configs_share_the_same_fields():
    for name in CONFIG_NAMES:
        cfg = getattr(settings, name)
        missing = {"base_url", "credential_ref", "timeout", "enabled"} - set(cfg)
        assert not missing, f"{name} 缺统一字段 {missing}"


def test_zabbix_refuses_when_disabled(monkeypatch):
    """地址或凭据缺一项就不建 client，报错口径与其他外部连接一致。"""
    from core.integrations.providers.zabbix import client as zabbix_client

    monkeypatch.setattr(zabbix_client, "_zapi", None)
    cfg = {"base_url": "http://zbx.example.com", "credential_ref": "", "timeout": 5, "enabled": False, "token": "", "user": "", "password": ""}
    with override_settings(ZABBIX_CONFIG=cfg), pytest.raises(ImproperlyConfigured, match="Zabbix 未配置"):
        asyncio.run(zabbix_client.get_zapi())


def test_aliyun_refuses_when_disabled():
    from core.integrations.aliyun.client import get_client

    cfg = {
        "base_url": "",
        "credential_ref": "",
        "timeout": 5,
        "region": "",
        "endpoints": {},
        "accounts": {"prod": {"access_key_id": "", "access_key_secret": ""}},
        "enabled": False,
    }
    with override_settings(ALIYUN_CONFIG=cfg), pytest.raises(ImproperlyConfigured, match="阿里云未配置"):
        get_client("prod")


def test_aliyun_refuses_incomplete_account():
    """全局 enabled 只表示「至少一套可用」，具体账号缺钥匙仍要单独拒掉（不再抛 KeyError）。"""
    from core.integrations.aliyun.client import get_client

    cfg = {
        "base_url": "",
        "credential_ref": "",
        "timeout": 5,
        "region": "cn-hangzhou",
        "endpoints": {},
        "accounts": {
            "prod": {"access_key_id": "ak", "access_key_secret": "sk"},
            "test": {"access_key_id": "", "access_key_secret": ""},
        },
        "enabled": True,
    }
    with override_settings(ALIYUN_CONFIG=cfg), pytest.raises(ImproperlyConfigured, match="test 账号"):
        get_client("test")


def test_autotask_refuses_when_disabled():
    from ingest.collectors.autotask.client import fetch_case

    cfg = {"base_url": "", "credential_ref": "", "timeout": 5, "enabled": False}
    with override_settings(AUTOTASK_CONFIG=cfg), pytest.raises(ImproperlyConfigured, match="AUTOTASK_BASE_URL"):
        asyncio.run(fetch_case())


def _documented_env_names() -> set[str]:
    """示例 env 里出现过的变量名（含被注释掉的行——示例以注释形式给默认值）。"""
    import re
    from pathlib import Path

    from django.conf import settings as django_settings

    root = Path(django_settings.BASE_DIR) / "envs" / "example"
    text = "".join(path.read_text(encoding="utf-8") for path in sorted(root.glob("*.env")))
    return set(re.findall(r"\b([A-Z][A-Z0-9_]{2,})\b", text))


@pytest.mark.parametrize("prefix", ("ZABBIX_", "ALIYUN_", "DIFY_", "AUTOTASK_", "INTEGRATION_PROBE_"))
def test_external_config_env_names_are_documented_in_example(prefix):
    """外部连接的环境变量必须进示例 env：新部署照抄模板时不能靠猜变量名。"""
    import re
    from pathlib import Path

    from django.conf import settings as django_settings

    base = (Path(django_settings.BASE_DIR) / "netops" / "settings" / "base.py").read_text(encoding="utf-8")
    # 只认真正从环境读的名字（os.environ.get / _env_or_file），排除 CONFIG 字典名
    used = {name for name in re.findall(r'(?:os\.environ\.get|_env_or_file)\(\s*"([A-Z][A-Z0-9_]+)"', base) if name.startswith(prefix)}
    missing = sorted(used - _documented_env_names())
    assert not missing, f"{prefix}* 未收录到 envs/example/*.env：{missing}"
