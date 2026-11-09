"""ASGI config for netops project.

导出模块级 ``application``：``gunicorn netops.asgi:application`` 与 Dockerfile 的
构建期冒烟检查（``django.setup()`` + import）都拿这个对象。

两层结构：
1. ``get_asgi_application()`` 完成 ``django.setup()``，产出只处理 http 的 Django handler；
2. 外面包一层 ``netops.lifespan.LifespanApp``，负责 lifespan 握手与启动/关闭钩子。
   Django 6.1 的 ASGIHandler 遇到 lifespan scope 会直接抛 ValueError，而 uvicorn 的
   ``lifespan=auto`` 会把这当成「app 不支持 lifespan」静默跳过——为什么必须包这一层、
   失败消息为什么必须是 ``*.failed``，见 ``netops/lifespan.py`` 模块注释。
"""

import os

from django.core.asgi import get_asgi_application

from netops.lifespan import LifespanApp, LifespanHook

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netops.settings')

django_application = get_asgi_application()

# 生命周期钩子的**唯一组合点**（与 MCP 工具注册同构：根基建不反向 import 域模块）。
# 当前为空——握手本身仍必须完成，否则 uvicorn 会把整个 app 判成「不支持 lifespan」，
# 以后往这里加的钩子就全都不会运行。
#
# 接 MCP Streamable HTTP（``/mcp``）时的形状：
#     import assets.mcp.tools  # noqa: F401 — import 即注册（工具挂到根 server）
#     from netops.mcp_server import mcp
#     mcp_http_app = mcp.streamable_http_app()          # 先建 app，session_manager 才有值
#     LIFESPAN_HOOKS = [mcp.session_manager.run]        # run() 全程只能调用一次
# 再按 path 把 ``/mcp`` 分发给 mcp_http_app、其余交给 django_application。
# 注意：换掉 ``--worker-class uvicorn_worker.UvicornWorker`` 就等于没有 lifespan，
# LifespanApp 会在第一个请求上告警一次。
LIFESPAN_HOOKS: list[LifespanHook] = []

application = LifespanApp(django_application, LIFESPAN_HOOKS)
