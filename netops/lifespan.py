"""ASGI lifespan 协议层：给只会处理 http 的 Django app 补上「启动 / 关闭」生命周期。

**为什么要自己包一层**（实测：Django 6.1.1 / uvicorn 0.53 / uvicorn-worker 0.4）：

- ``django.core.handlers.asgi.ASGIHandler.__call__`` 只认 ``scope["type"] == "http"``，
  其它一律 ``raise ValueError("Django can only handle ASGI/HTTP connections, not lifespan.")``
  ——Django 6.1 **不再**自带 lifespan 握手（旧版那两段 startup/shutdown 应答已移除）。
- uvicorn 默认 ``lifespan="auto"``：启动时给 app 发一根 ``lifespan`` scope，app 一抛异常就
  记一行 info ``ASGI 'lifespan' protocol appears unsupported.``，然后**照常服务**。
  于是 ``gunicorn netops.asgi:application`` 下任何依赖 lifespan 的东西（MCP 的
  ``StreamableHTTPSessionManager.run()`` 任务组、连接池、后台任务）都永远不启动，
  日志里还只有一行看着无害的提示——极易误判成"已经生效"。
- 所以本模块**只接管 lifespan scope**，http / websocket 原样转给 Django；同时把
  lifespan 的 ``scope["state"]`` 透给每个请求 scope（ASGI Lifespan State），钩子可以把
  进程级资源放进去给请求侧取用。

**失败语义**（同样实测）：uvicorn 的 auto 模式只有收到 ``lifespan.startup.failed``
才会把 ``should_exit`` 置真；**直接抛异常会被当成"app 不支持 lifespan"静默降级**。
所以钩子抛错必须回 ``*.failed`` 消息，traceback 另用 ``logger.exception`` 落进日志。

钩子是「无参 → 异步上下文管理器」的工厂（``@asynccontextmanager`` 函数，或
``session_manager.run()`` 这类自带的方法）：按列表顺序进入，由 ``AsyncExitStack``
逆序退出；startup 中途失败会回滚已进入的钩子。

    @asynccontextmanager
    async def pool():
        conn = await create_pool()
        try:
            yield
        finally:
            await conn.aclose()

    application = LifespanApp(django_application, [pool])

组合责任在 ``netops/asgi.py``（与 MCP 工具注册同构：根基建不反向 import 任何域模块）。
本模块不依赖 Django，import 顺序无约束。
"""

from __future__ import annotations

import logging
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from typing import Any, Awaitable, Callable, Iterable

logger = logging.getLogger("netops.lifespan")

Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]
LifespanHook = Callable[[], AbstractAsyncContextManager[Any]]

_NO_LIFESPAN_WARNING = "ASGI 服务器没有发送 lifespan.startup，启动钩子未执行；检查 --worker-class 是否还是 uvicorn_worker.UvicornWorker、uvicorn 的 --lifespan 是否被关掉"


class LifespanApp:
    """包在 Django ASGI handler 外面的 lifespan 层。

    每个 gunicorn worker 进程一份实例：``start`` 时进入全部钩子，``shutdown`` 时逆序退出。
    钩子清单在构造时固定，运行期不再变动（避免"请求打到一半钩子被换掉"）。
    """

    def __init__(self, app: ASGIApp, hooks: Iterable[LifespanHook] = ()) -> None:
        self.app = app
        self.hooks = list(hooks)
        self.state: dict[str, Any] = {}
        self._stack = AsyncExitStack()
        self._started = False
        self._lifespan_supported = False
        self._warned = False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            self._lifespan_supported = True
            # uvicorn 在 lifespan scope 里带的 state 是它自己持有的那个 dict；沿用它，
            # 让钩子放进去的资源能被同一个进程里的请求 scope 看到。
            self.state = scope.setdefault("state", self.state)
            await self._lifespan(receive, send)
            return

        if not self._lifespan_supported and not self._warned:
            # 换成 sync/gthread worker、或 uvicorn --lifespan off 时，钩子会**静默**不跑。
            # 只在第一个请求上告警一次，既不刷日志也不让这种配置悄悄混过去。
            self._warned = True
            logger.warning(_NO_LIFESPAN_WARNING)

        # 不改原 scope（ASGI 服务器可能复用它），浅拷贝一份注入 state。
        await self.app({**scope, "state": self.state}, receive, send)

    async def _lifespan(self, receive: Receive, send: Send) -> None:
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await self._startup(send)
            elif message["type"] == "lifespan.shutdown":
                await self._shutdown(send)
                return

    async def _startup(self, send: Send) -> None:
        if self._started:
            # 不规范的重复握手：只应答，绝不把钩子再进一遍（session_manager.run()
            # 这类钩子明确只能调用一次，重进必然炸）。
            await send({"type": "lifespan.startup.complete"})
            return
        try:
            for hook in self.hooks:
                await self._stack.enter_async_context(hook())
        except Exception as exc:
            logger.exception("ASGI lifespan startup 失败，回滚已进入的钩子")
            await self._rollback()
            await send({"type": "lifespan.startup.failed", "message": f"{type(exc).__name__}: {exc}"})
        else:
            self._started = True
            logger.debug("ASGI lifespan startup 完成：%d 个钩子", len(self.hooks))
            await send({"type": "lifespan.startup.complete"})

    async def _shutdown(self, send: Send) -> None:
        try:
            await self._stack.aclose()
        except Exception as exc:
            logger.exception("ASGI lifespan shutdown 失败")
            await send({"type": "lifespan.shutdown.failed", "message": f"{type(exc).__name__}: {exc}"})
        else:
            self._started = False
            await send({"type": "lifespan.shutdown.complete"})

    async def _rollback(self) -> None:
        """startup 失败后收尾；退出钩子再抛错不能盖掉原始异常、更不能冒到 uvicorn。"""
        try:
            await self._stack.aclose()
        except Exception:
            logger.exception("ASGI lifespan 回滚钩子时再次失败")
