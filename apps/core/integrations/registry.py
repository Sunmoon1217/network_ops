"""provider 注册表与实例取用：纯 dict，不 import models、不 import 任何业务域。

注册方向永远是「业务域 → core」：

.. code-block:: python

    # apps/ingest/apps.py
    def ready(self):
        from core.integrations import register_provider
        from core.integrations.providers.zabbix import ZabbixProvider

        register_provider(ZabbixProvider())

这条约束是为了避免 ``core → ingest`` 反向依赖（会直接循环导入：ingest 的 ready() 正在
import core 的这个模块）。``tests/core/test_layering.py`` 会扫 core 的 import 兜住。

**为什么实例不放数据库**：client 绑着 session / 连接池 / 事件循环，天然是进程内的东西；
跨进程「谁持有什么实例」只能靠外化的健康状态（``IntegrationHealth``，由 beat 的
``core.integrations.probe_all`` 周期写入，见 ``health.py`` 与 ``handbook/integrations.md``），
不是靠注册表。
"""

from __future__ import annotations

import logging
from typing import Any

from .provider import Provider

logger = logging.getLogger(__name__)

DEFAULT_INSTANCE = "default"

_providers: dict[tuple[str, str], Provider] = {}


def register_provider(provider: Provider) -> None:
    """登记一个 provider。幂等：同键重复登记以最后一次为准（测试可借此替换实现）。"""
    _providers[(provider.system, provider.instance)] = provider


def get_provider(system: str, instance: str = DEFAULT_INSTANCE) -> Provider:
    """按 (system, instance) 取 provider；未注册立刻报错，不做「悄悄返回空」的兼容。"""
    try:
        return _providers[(system, instance)]
    except KeyError:
        registered = ", ".join(f"{s}/{i}" for s, i in sorted(_providers)) or "无"
        raise LookupError(f"未注册的集成：{system}/{instance}（已注册：{registered}）") from None


async def acquire(system: str, instance: str = DEFAULT_INSTANCE) -> Any:
    """取 client 实例（async 入口：同步实现的 provider 在内部直接返回）。"""
    return await get_provider(system, instance).acquire()


def acquire_sync(system: str, instance: str = DEFAULT_INSTANCE) -> Any:
    """同步栈（DRF 线程池 / management command）取 client 实例。

    **只有显式提供 ``acquire_sync()`` 的 provider 可用**。Zabbix 这类 async client 不提供，
    这里直接 ``TypeError``——绝不在同步栈里偷偷 ``asyncio.run``（会跟 Celery 任务自己的
    循环打架，也会让 session 绑到错误的 loop 上）。
    """
    provider = get_provider(system, instance)
    acquire_fn = getattr(provider, "acquire_sync", None)
    if acquire_fn is None:
        raise TypeError(f"{system}/{instance} 只提供异步 acquire()；同步栈请改为 await acquire() 或让 provider 实现 acquire_sync()")
    return acquire_fn()


async def release_all() -> None:
    """释放全部实例（ASGI shutdown / Celery 子进程退出）。

    单个失败只记日志：收尾阶段不能让一个外部系统挡住其它进程退出。
    """
    for (system, instance), provider in list(_providers.items()):
        try:
            await provider.release()
        except Exception:
            logger.exception("释放集成实例失败 %s/%s", system, instance)


def describe_all() -> list[dict[str, Any]]:
    """已注册实例的自描述快照（``GET /api/integrations/`` 的供数之一）。"""
    return [provider.describe() for provider in _providers.values()]


def registered() -> list[tuple[str, str]]:
    """已注册的 (system, instance) 键，按字典序。测试与排障用。"""
    return sorted(_providers)
