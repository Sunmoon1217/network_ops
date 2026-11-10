"""MCP 基建：根 server 单例 + 工具执行包装（``with_db_lifecycle``）。

工具不在本模块自注册：各域只提供纯函数，由 ``llmtools/tools.py`` 汇总名单、统一包装后
``mcpserver.add_tool()``；接线责任在 ``llmtools/__init__.py``（import 本包即接入）。
本模块导入即建 server，不做任何网络监听——传输层接线在 ``netops.asgi``。

两条防循环硬规矩（禁止 import 域模块与 core 业务模块）、``with_db_lifecycle`` 的必要性
与 ``functools.wraps`` 的约束见 docs/llmtools.md
"""

from functools import wraps

from django.conf import settings
from django.db import close_old_connections
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

#: MCP server 单例（角色等同 Django 的 ``admin.site``）。HTTP 传输的 session_manager 在
#: ``streamable_http_app()`` 里懒创建，全进程只能调一次（重复调用会让旧 ASGI app 持有失效 manager）。
mcpserver = MCPServer(
    "netops",
    instructions=(
        "网络运维管理平台的 MCP Server。实体由各域注册到 llmtools.registry，"
        "通用工具只认注册表（当前已接入资产域：设备、接口、路由、IP、ARP、负载均衡等）。"
        "所有工具返回结构化 JSON；未声明的字段/操作符会报错而不是被忽略。"
        "需要组合条件、多字段排序或字段投影时用 query（QueryPlan）。"
    ),
)


def build_transport_security() -> TransportSecuritySettings:
    """MCP 传输层白名单跟随 ``ALLOWED_HOSTS``——不跟随就会 421 ``Invalid Host header``。

    ``streamable_http_app()`` 的 ``host`` 默认 ``127.0.0.1``，SDK 便自动把白名单写死成
    localhost 三件套，用 IP / 域名访问的请求在到达工具之前就被挡掉，而 Django 侧因为
    ``ALLOWED_HOSTS`` 放开却是通的（两套口径不一致，很难排查）。

    ``*`` 等价于 Django 的「不校验」，直接关防护；否则放行这些域名的任意端口。裸 host
    也要给一份：SDK 只认 ``host:*`` 通配，而默认端口下 Host 头不带端口（nginx 的
    ``$http_host`` 就是这样）。IPv6 请写成 ``[::1]``。
    """
    hosts = [h for h in settings.ALLOWED_HOSTS if h and h != "*"]
    if not hosts:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    return TransportSecuritySettings(
        allowed_hosts=hosts + [f"{h}:*" for h in hosts],
        allowed_origins=[f"{scheme}://{h}{port}" for h in hosts for scheme in ("http", "https") for port in ("", ":*")],
    )


def with_db_lifecycle(fn):
    """工具函数的执行包一层数据库连接回收（调用前清坏连接、调用后必关）。"""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        close_old_connections()
        try:
            return fn(*args, **kwargs)
        finally:
            close_old_connections()

    return wrapper
