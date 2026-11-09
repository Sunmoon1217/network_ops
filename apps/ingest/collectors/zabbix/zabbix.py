"""Zabbix API 客户端：**进程级单例**（全局唯一）+ 懒创建 + 并发安全 + response 对象化。

``get_zapi()`` 返回 ``TypedZabbixAPI``（``AsyncZabbixAPI`` 的子类）。子类只做一件事：
给每个用到的官方 API 对象配一个 ``<object>_get`` 扩展方法 —— 方法内部仍按官方形态
``await self.<object>.get(**params)``，再把 JSON-RPC ``result`` **校验并实例化**成
``schemas.py`` 里的 DTO 列表。**不写额外功能**：ID 提取、映射组装、条件组合、峰值
计算等编排一律留在 ``queries.py``，扩展方法只有「调 API → 校验 → 实例化」两步。

允许**有限的参数固化**：只固化保证 DTO 能校验通过的字段参数（``output`` /
``selectHosts`` / ``object``），过滤条件（``groupids`` / ``hostids`` / ``itemids`` /
``search`` / ``limit`` / ``time_*`` ...）一律由调用方按官方 API 原样传入；固化项以
本类为准（同名传参会被覆盖），其余参数原样透传。

用法（`await` 只能在 async 函数里用，模块顶层没有事件循环，不能写
`zapi = await get_zapi()`）：
    from apps.ingest.collectors.zabbix import get_zapi

    async def collect_items():
        zapi = await get_zapi()
        return await zapi.item_get(limit=10)                # -> list[ZAPIItem]

    # countOutput 等返回标量的调用，直接用官方动态 API（不经过 DTO 校验）：
    #   count = await zapi.host.get(groupids=ids, countOutput=1)

同步上下文（Celery 任务 / management command）用 asyncio.run 把「取实例 + 业务调用」
包在**同一个** loop 里；单例绑定创建它的 loop，分两次 asyncio.run 会导致第二次重建：
    import asyncio

    items = asyncio.run(collect_items())

为什么不在模块 import 时创建（旧版写法的坑）：
    - `aiohttp.ClientSession` 必须在事件循环内创建，import 期没有（或不是最终那个）
      running loop，session 会绑错循环甚至直接炸；
    - `AsyncZabbixAPI.__init__` 内部会创建 session 并做**同步版本探测**，同样要求 running loop；
    - Celery worker / ASGI / 测试各自有独立进程与循环，import 即建的实例无法跨循环复用。

生命周期：
    - `get_zapi()`：懒创建 + 登录（token 优先，其次 user/password），缓存在模块级；
      并发调用经 asyncio.Lock 串行，永远返回同一个实例；
    - 已有实例时只做健康检查（同一事件循环且 session 未关闭），命中即零开销返回；
    - 事件循环变化（如测试里多个 loop）或 session 已关时，先释放旧实例再重建；
    - `close_zapi()`：显式释放（登出 + 关 session），供进程收尾 / 长期任务结束后回收。
"""

import asyncio
from typing import Any, TypeVar

from aiohttp import ClientSession, ClientTimeout
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from pydantic import BaseModel
from zabbix_utils.aioapi import AsyncZabbixAPI

from .schemas import ZAPIGroup, ZAPIHistory, ZAPIHost, ZAPIItem, ZAPIProblem, ZAPITrigger

T = TypeVar("T", bound=BaseModel)

# 有限固化：只固定「保证 DTO 必填字段能取到」的输出口径，过滤条件仍由调用方按官方 API 给
_ITEM_PARAMS: dict[str, Any] = {
    "output": ["itemid", "name", "key_", "lastvalue", "lastclock"],
    "selectHosts": ["hostid", "host", "name"],  # 带出主机，供 ZAPIItem.hosts 实例化
}
_HISTORY_PARAMS: dict[str, Any] = {"output": "extend"}  # 保证 itemid / clock / value
_TRIGGER_PARAMS: dict[str, Any] = {
    "selectHosts": ["hostid", "host", "name"],
    "output": ["triggerid", "name", "opdata", "priority"],
}
_PROBLEM_PARAMS: dict[str, Any] = {"output": "extend", "object": 0}  # 只取触发器类问题


class TypedZabbixAPI(AsyncZabbixAPI):
    """官方 API 的薄封装：``<object>_get`` = 一次官方 ``<object>.get`` + 结果校验实例化。

    两条硬约束（对照 zabbix_utils 2.0.2 的 aioapi.py 实测）：
        1. **不覆写** ``__init__`` / ``login`` / ``logout``：父类构造会做同步版本探测，
           登录态与 session 存在 name-mangled 私有属性里，动了就破坏单例生命周期；
        2. **不覆写** ``__getattr__``：父类对**任意**未知属性都返回 ``APIObject``（连拼错的
           属性名都不会抛 AttributeError），动态分派不能被截断；扩展方法因此统一叫
           ``<object>_get``，避开 ``item`` / ``history`` / ``trigger`` 等动态对象名。

    ``_objects`` 是唯一的校验出口：result 必须是列表，逐条 ``model_validate``；
    失败原样抛（pydantic ``ValidationError`` 带字段信息），不降级成空结果。
    """

    @staticmethod
    def _objects(result: Any, model: type[T], method: str) -> list[T]:
        """校验 result 形态并逐条实例化成 DTO。"""
        if not isinstance(result, list):
            raise TypeError(f"{method} 的 result 不是列表，实际为 {type(result).__name__}")
        return [model.model_validate(row) for row in result]

    async def hostgroup_get(self, **params: Any) -> list[ZAPIGroup]:
        """官方 ``hostgroup.get`` → ``list[ZAPIGroup]``；参数原样透传。"""
        return self._objects(await self.hostgroup.get(**params), ZAPIGroup, "hostgroup.get")

    async def host_get(self, **params: Any) -> list[ZAPIHost]:
        """官方 ``host.get`` → ``list[ZAPIHost]``；参数原样透传。"""
        return self._objects(await self.host.get(**params), ZAPIHost, "host.get")

    async def item_get(self, **params: Any) -> list[ZAPIItem]:
        """官方 ``item.get`` → ``list[ZAPIItem]``；固化 output / selectHosts。"""
        return self._objects(await self.item.get(**(params | _ITEM_PARAMS)), ZAPIItem, "item.get")

    async def history_get(self, **params: Any) -> list[ZAPIHistory]:
        """官方 ``history.get`` → ``list[ZAPIHistory]``；固化 output=extend。"""
        return self._objects(await self.history.get(**(params | _HISTORY_PARAMS)), ZAPIHistory, "history.get")

    async def trigger_get(self, **params: Any) -> list[ZAPITrigger]:
        """官方 ``trigger.get`` → ``list[ZAPITrigger]``；固化 output / selectHosts。"""
        return self._objects(await self.trigger.get(**(params | _TRIGGER_PARAMS)), ZAPITrigger, "trigger.get")

    async def problem_get(self, **params: Any) -> list[ZAPIProblem]:
        """官方 ``problem.get`` → ``list[ZAPIProblem]``；固化 output=extend / object=0。"""
        return self._objects(await self.problem.get(**(params | _PROBLEM_PARAMS)), ZAPIProblem, "problem.get")


_zapi: TypedZabbixAPI | None = None
_zapi_loop: asyncio.AbstractEventLoop | None = None
_zapi_lock = asyncio.Lock()


async def get_zapi() -> TypedZabbixAPI:
    """取全局唯一的 TypedZabbixAPI，未创建（或已失效）时创建并登录。"""
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
        _zapi = TypedZabbixAPI(url=cfg["url"], client_session=session)

        if cfg["token"]:
            await _zapi.login(token=cfg["token"])
        else:
            if not cfg["user"] or not cfg["password"]:
                raise ImproperlyConfigured("Zabbix 凭据缺失：ZABBIX_TOKEN 或 ZABBIX_USER/ZABBIX_PASSWORD 至少一组")
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


async def _dispose(zapi: TypedZabbixAPI) -> None:
    """释放一个实例：先登出（回收服务端会话），再关 session；失败不阻断关闭。"""
    try:
        await zapi.logout()
    except Exception:  # noqa: BLE001 —— 网络已断/会话已失效时登出必然失败，忽略
        pass
    if not zapi.client_session.closed:
        await zapi.client_session.close()
