"""provider 注册表与实例取用：纯 dict，不 import models、不 import 任何业务域。

注册方向永远「业务域 → core」（各域在 ``ready()`` 里 ``register_provider``），否则会循环
导入。实例刻意不放数据库：client 绑着 session / 连接池 / 事件循环，是进程内的东西；
跨进程只能看外化的 ``IntegrationHealth``。见 handbook/integrations.md。
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
    """同步栈取 client 实例；只有实现了 ``acquire_sync()`` 的 provider 可用。

    绝不在同步栈里偷偷 ``asyncio.run``（会跟 Celery 任务自己的循环打架）。
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
    """已注册实例的自描述快照（``GET /api/core/integrations/`` 的供数之一）。"""
    return [provider.describe() for provider in _providers.values()]


def registered() -> list[tuple[str, str]]:
    """已注册的 (system, instance) 键，按字典序。测试与排障用。"""
    return sorted(_providers)
