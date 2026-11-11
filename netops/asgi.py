"""ASGI config for netops project.

导出模块级 ``application``：``gunicorn netops.asgi:application`` 与 Dockerfile 的
构建期冒烟检查（``django.setup()`` + import）都拿这个对象。

四层结构：
1. ``get_asgi_application()`` 完成 ``django.setup()``，产出只处理 http 的 Django handler；
2. ``_dispatch`` 按路径分发：``/mcp*`` 给 MCP 的 Streamable HTTP 子应用，其余给 Django；
3. MCP 子应用外面包 ``netops.mcp_gateway.McpGuardMiddleware``（匿名限流，只管 /mcp）；
4. 最外面是 ``netops.lifespan.LifespanApp``，负责 lifespan 握手与启动/关闭钩子
   （MCP 的 ``session_manager.run()`` 就是其中一个钩子）。Django 6.1 的 ASGIHandler
   遇到 lifespan scope 会直接抛 ValueError，而 uvicorn 的 ``lifespan=auto`` 会把这当成
   「app 不支持 lifespan」静默跳过——为什么必须包这一层、失败消息为什么必须是
   ``*.failed``，见 ``netops/lifespan.py`` 模块注释。

``MCP_ENABLED=0`` 时不 import ``llmtools``、不建子应用、不装钩子，`/mcp` 明确回 404
（不能交给 Django——它会落到 SPA 兜底返回 ``index.html``）。
"""

import os

from django.conf import settings
from django.core.asgi import get_asgi_application

from netops.lifespan import LifespanApp
from netops.mcp_gateway import McpGuardMiddleware, is_mcp_path, send_disabled

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netops.settings")

# 先完成 Django 初始化，出口层才能安全 import 各域 models / serializers。
django_application = get_asgi_application()

if settings.MCP_ENABLED:
    from llmtools import build_transport_security, mcpserver  # noqa: E402 — import 即接线（实体 + 工具）

    # Streamable HTTP 子应用：内部自带 /mcp 路由；构建之后 mcpserver.session_manager 才存在。
    # transport_security 必须显式传——默认值只信任 localhost，用 IP/域名访问会 421。
    # 外面再包一层出口护栏（匿名限流）；不套在 _dispatch 上，免得每条 /api 请求都过卡。
    mcp_http_app = McpGuardMiddleware(mcpserver.streamable_http_app(transport_security=build_transport_security()))

    # 生命周期钩子的唯一组合点：MCP 的 session_manager.run() 必须在 lifespan 里进入一次
    # （全进程只能调用一次），否则 tool 调用会挂在没有任务组的 manager 上。
    LIFESPAN_HOOKS = [mcpserver.session_manager.run]
else:
    mcp_http_app = None
    LIFESPAN_HOOKS = []


async def _dispatch(scope, receive, send):
    """按路径分发：/mcp* → MCP 子应用，其余 → Django。

    不用 Starlette Mount 的原因：streamable_http_app() 内部路由就是 /mcp，
    Mount("/mcp", ...) 会把端点叠成 /mcp/mcp；Mount("/", ...) 又会被 Django
    侧整体吞掉。lifespan scope 不在这里处理——它已在更外层被 LifespanApp 接走。
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
