"""Zabbix 在 core 注册表里的 provider：只转发，不复制 client 逻辑。

事件循环亲和判定留在 ``client.get_zapi``（Celery 每个采集任务一个新 loop），
不上提到 registry——否则 core 得懂事件循环。详见 handbook/integrations.md。
"""

from __future__ import annotations

from typing import Any

from django.conf import settings

from .client import TypedZabbixAPI, close_zapi, get_zapi


class ZabbixProvider:
    """Zabbix 默认实例：``acquire`` / ``release`` 直接转给 client，单例与锁都在那里。"""

    system = "zabbix"
    instance = "default"

    async def acquire(self) -> TypedZabbixAPI:
        return await get_zapi()

    async def release(self) -> None:
        await close_zapi()

    def describe(self) -> dict[str, Any]:
        """自描述（不含凭据值，只说「用哪种方式登录」）。"""
        cfg = settings.ZABBIX_CONFIG
        return {
            "system": self.system,
            "instance": self.instance,
            "base_url": cfg["base_url"],
            "configured": cfg["enabled"],
            "auth": "token" if cfg["token"] else "user_password",
            "timeout": cfg["timeout"],
        }
