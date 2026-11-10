"""MCP 基建：根 server 单例 + 工具执行包装（与 Django admin 同构：根注册表，叶子装饰）。

**根单例** ``mcp = MCPServer("netops", ...)``：通用工具模块（``core.mcp.tools``）
顶层 ``from core.mcp.server import mcp`` + ``@mcp.tool()`` 直接装饰，**import 即注册**。
组合责任在调用方：``netops/asgi.py``（挂 ``/mcp`` 时）或测试，import 一次域模块即接入。

⚠ 两条防循环硬规矩：
1. 本模块**禁止 import 任何域模块**（``assets`` / ``analysis`` / ``docs`` …）——
   叶子 import 本模块，本模块再 import 叶子即成环。
2. 即使物理上在 ``apps/core/mcp/``，本子包也**禁止 import core 的业务模块**
   （``core.models`` / ``core.api`` / ``core.permissions`` / ``core.tasks``）：
   MCP 只提供查询基建，不读用户、权限、任务数据。

**执行包装** ``with_db_lifecycle``：MCP 同步工具跑在 AnyIO 短命工作线程，不像 Django 视图
自带 request_finished 时的 close_old_connections——连接会随线程对象滞留到 GC 才关闭
（测试库销毁时报 "being accessed by other users" 就是它）。包装在调用前后各补一次
close_old_connections()：本项目 CONN_MAX_AGE 默认 0，调用结束即关连接，语义与一次
Web 请求的生命周期对齐。``functools.wraps`` 必须保留——SDK 沿 __wrapped__ 链读签名
生成入参 schema，去掉 wraps 工具就没有参数说明书了。

本模块导入即建 server，不做任何网络监听；对外服务（Streamable HTTP 挂进
netops.asgi / manage.py stdio）属于传输层接线。
"""

from functools import wraps

from django.conf import settings
from django.db import close_old_connections
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

mcp = MCPServer(
    "netops",
    instructions=(
        "网络运维管理平台的 MCP Server。实体由各域注册到 core.mcp.registry，"
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
