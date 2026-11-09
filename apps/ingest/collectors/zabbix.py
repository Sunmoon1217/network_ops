"""Zabbix API 客户端：**进程级单例**（全局唯一）+ 懒创建 + 并发安全。

为什么不在模块 import 时创建（旧版写法的坑）：
    - `aiohttp.ClientSession` 必须在事件循环内创建，import 期没有（或不是最终那个）
      running loop，session 会绑错循环甚至直接炸；
    - `AsyncZabbixAPI.__init__` 内部会创建 session 并做版本探测，同样要求 running loop；
    - Celery worker / ASGI / 测试各自有独立进程与循环，import 即建的实例无法跨循环复用。

用法：
    from apps.ingest.collectors.zabbix import get_zapi

    zapi = await get_zapi()
    hosts = await zapi.host.get({"output": ["hostid", "name"]})

生命周期：
    - `get_zapi()`：懒创建 + 登录（token 优先，其次 user/password），缓存在模块级；
      并发调用经 asyncio.Lock 串行，永远返回同一个实例；
    - 已有实例时只做健康检查（同一事件循环且 session 未关闭），命中即零开销返回；
    - 事件循环变化（如测试里多个 loop）或 session 已关时，先释放旧实例再重建；
    - `close_zapi()`：显式释放（登出 + 关 session），供进程收尾 / 长期任务结束后回收。
"""

import asyncio

from aiohttp import ClientSession, ClientTimeout
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from zabbix_utils.aioapi import AsyncZabbixAPI

_zapi: AsyncZabbixAPI | None = None
_zapi_loop: asyncio.AbstractEventLoop | None = None
_zapi_lock = asyncio.Lock()


async def get_zapi() -> AsyncZabbixAPI:
    """取全局唯一的 AsyncZabbixAPI，未创建（或已失效）时创建并登录。"""
    global _zapi, _zapi_loop

    async with _zapi_lock:
        loop = asyncio.get_running_loop()

        if _zapi is not None:
            if _zapi_loop is loop and not _zapi.client_session.closed:
                return _zapi
            await _dispose(_zapi)
            _zapi = None

        cfg = settings.ZABBIX_CONFIG
        if not cfg["url"]:
            raise ImproperlyConfigured("ZABBIX_URL 未配置（settings.ZABBIX_CONFIG）")

        # session 自己创建、自己关：不依赖库的 __internal_client（它只认 user/password
        # 登录后的 logout 才会关；token 登录或从未登录时没有公开的关闭出口）
        session = ClientSession(timeout=ClientTimeout(total=cfg["timeout"]))
        _zapi = AsyncZabbixAPI(url=cfg["url"], client_session=session)

        if cfg["token"]:
            await _zapi.login(token=cfg["token"])
        else:
            if not cfg["user"] or not cfg["password"]:
                raise ImproperlyConfigured(
                    "Zabbix 凭据缺失：ZABBIX_TOKEN 或 ZABBIX_USER/ZABBIX_PASSWORD 至少一组"
                )
            await _zapi.login(user=cfg["user"], password=cfg["password"])

        _zapi_loop = loop
        return _zapi


async def close_zapi() -> None:
    """登出并关闭单例，下次 get_zapi 会重建。幂等：无实例时直接返回。"""
    global _zapi, _zapi_loop

    async with _zapi_lock:
        if _zapi is None:
            return
        await _dispose(_zapi)
        _zapi = None
        _zapi_loop = None


async def _dispose(zapi: AsyncZabbixAPI) -> None:
    """释放一个实例：先登出（回收服务端会话），再关 session；失败不阻断关闭。"""
    try:
        await zapi.logout()
    except Exception:  # noqa: BLE001 —— 网络已断/会话已失效时登出必然失败，忽略
        pass
    if not zapi.client_session.closed:
        await zapi.client_session.close()
