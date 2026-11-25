"""ASGI 入口：导出模块级 ``application``（gunicorn 与构建期冒烟检查都用它）。

分层：Django handler → ``_dispatch``（/mcp* 交 MCP，其余交 Django，MCP 外再包匿名限流）
→ ``LifespanApp``（握手 + LIFESPAN_HOOKS）。生命周期细节见 netops/lifespan.py 与 handbook/llmtools.md。
``MCP_ENABLED=0`` 时不建子应用、不装钩子，/mcp 明确回 404。
"""

import os
from contextlib import asynccontextmanager

from django.conf import settings
from django.core.asgi import get_asgi_application

from netops.lifespan import LifespanApp
from netops.mcp_gateway import McpGuardMiddleware, is_mcp_path, send_disabled

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netops.settings")

# 先完成 Django 初始化，出口层才能安全 import 各域 models / serializers。
django_application = get_asgi_application()


@asynccontextmanager
async def _release_integrations():
    """进程收尾释放外部 client（core.integrations.release_all）；单个失败不阻塞 shutdown。"""
    try:
        yield
    finally:
        from core.integrations import release_all

        await release_all()


if settings.MCP_ENABLED:
    from llmtools import build_transport_security, mcpserver  # noqa: E402 — import 即接线（实体 + 工具）

    # Streamable HTTP 子应用：内部自带 /mcp 路由。transport_security 必须显式传
    # （默认只信任 localhost，用 IP/域名访问会 421）；外层是匿名限流护栏。
    mcp_http_app = McpGuardMiddleware(mcpserver.streamable_http_app(transport_security=build_transport_security()))

    # 生命周期钩子只在这里组合：session_manager.run() 全进程只能进入一次。
    # _release_integrations 排在最后 → AsyncExitStack 逆序退出时它先执行。
    LIFESPAN_HOOKS = [mcpserver.session_manager.run, _release_integrations]
else:
    mcp_http_app = None
    LIFESPAN_HOOKS = [_release_integrations]


async def _dispatch(scope, receive, send):
    """按路径分发：/mcp* → MCP 子应用，其余 → Django；lifespan 由外层 LifespanApp 处理。

    不用 Starlette Mount：streamable_http_app() 内部路由已是 /mcp，Mount 会叠成 /mcp/mcp。
    """
    path = scope.get("path", "")
    if scope["type"] in ("http", "websocket") and is_mcp_path(path):
        if mcp_http_app is not None:
            await mcp_http_app(scope, receive, send)
        elif scope["type"] == "http":
            await send_disabled(send)
        else:
            await send({"type": "websocket.close", "code": 1008})
        return
    await django_application(scope, receive, send)


application = LifespanApp(_dispatch, LIFESPAN_HOOKS)
