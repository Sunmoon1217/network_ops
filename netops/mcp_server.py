"""MCP 基建：根 server 单例 + 工具执行包装（与 Django admin 同构：根注册表，叶子装饰）。

**根单例** ``mcp = MCPServer("netops", ...)``：各域工具模块（如 ``apps/assets/mcp/tools.py``）
顶层 ``from netops.mcp_server import mcp`` + ``@mcp.tool()`` 直接装饰，**import 域模块即完成注册**。
组合责任在调用方：netops/asgi.py（挂 ``/mcp`` 时）或测试，``import assets.mcp.tools`` 一行接一个域。

⚠ 防循环硬规矩（与 settings 的防循环规矩同性质）：**本模块禁止 import 任何域工具模块**
——叶子 import 本模块，本模块再 import 叶子即成环。注册清单只许出现在调用方。

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

from django.db import close_old_connections
from mcp.server import MCPServer

mcp = MCPServer(
    "netops",
    instructions="网络运维管理平台的 MCP Server。当前提供设备库查询工具（设备、设备组）；所有工具返回结构化 JSON，字符串查询条件留空即不过滤，主机名匹配大小写不敏感。",
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
