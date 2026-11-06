"""
ASGI config for netops project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netops.settings')

# 先完成 Django 初始化，域工具模块才能安全 import models。
django_asgi_app = get_asgi_application()

import assets.mcp.tools  # noqa: E402,F401 — import 即注册（工具挂到 netops.mcp_server.mcp）
from netops.mcp_server import mcp  # noqa: E402

# Streamable HTTP 子应用：内部自带 /mcp 路由与 lifespan（进入 mcp.session_manager.run()）。
# 构建之后 mcp.session_manager 才存在；本模块导入即完成全部接线，不额外监听端口。
mcp_asgi_app = mcp.streamable_http_app()


async def _dispatch(scope, receive, send):
    """按路径分发：/mcp* → MCP 子应用，其余 → Django；lifespan 只给 MCP。

    不用 Starlette Mount 的原因：streamable_http_app() 内部路由就是 /mcp，
    Mount("/mcp", ...) 会把端点叠成 /mcp/mcp；Mount("/", ...) 又会被 Django
    侧整体吞掉。手写分发器还顺带解决了 lifespan——Django 的 ASGI handler
    不支持 lifespan 协议，而 MCP 子应用自带的 lifespan 正是
    session_manager.run()（文档强调的「everyone forgets」那行），直接把
    lifespan scope 转发给它即可，无需宿主再包一层。
    """
    if scope["type"] == "lifespan":
        await mcp_asgi_app(scope, receive, send)
        return
    path = scope.get("path", "")
    if path == "/mcp" or path.startswith("/mcp/"):
        await mcp_asgi_app(scope, receive, send)
    else:
        await django_asgi_app(scope, receive, send)


application = _dispatch
