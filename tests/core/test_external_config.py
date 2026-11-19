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
    from cloud.client import get_client

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
    from cloud.client import get_client

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
    from ingest.collectors.autotask.autotask import fetch_case

    cfg = {"base_url": "", "credential_ref": "", "timeout": 5, "enabled": False}
    with override_settings(AUTOTASK_CONFIG=cfg), pytest.raises(ImproperlyConfigured, match="AUTOTASK_BASE_URL"):
        asyncio.run(fetch_case())
