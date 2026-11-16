"""Zabbix 在 core 注册表里的 provider：只做转发，不复制 client 逻辑。

**事件循环亲和为什么留在这条实现链上**：``apps/ingest/tasks.py`` 每个采集任务都
``asyncio.run(collect(source))``——一个 Celery 任务一个新 loop。client 单例因此必须
「绑定的 loop 不是当前 loop 就释放重建」（``client.get_zapi`` 里的 ``_zapi_loop`` 判定）。

这条知识不能上提到 ``core.integrations.registry``：那样 core 就得懂事件循环，provider
变成哑的。现在的分工是——registry 只说「取实例 / 释放实例」，provider 实现里怎么判断
实例还活着（loop 亲和 + session 未关）完全自治。
"""

from __future__ import annotations

from typing import Any

from django.conf import settings

from .client import TypedZabbixAPI, close_zapi, get_zapi


class ZabbixProvider:
    """Zabbix 默认实例。

    ``acquire`` / ``release`` 直接转给 client 的 ``get_zapi`` / ``close_zapi``——单例与
    并发锁都在那里，provider 不持有第二份状态（两份状态是「以为释放了其实没有」的根源）。
    """

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
            "base_url": cfg["url"],
            "configured": bool(cfg["url"] and (cfg["token"] or (cfg["user"] and cfg["password"]))),
            "auth": "token" if cfg["token"] else "user_password",
            "timeout": cfg["timeout"],
        }
