"""MCP 根 server 单例（与 Django 的 admin.site 同构：根注册表，叶子装饰）。

本模块**只持有** ``mcp = MCPServer("netops", ...)``，不做任何注册：各域工具模块
（如 ``apps/assets/mcp/tools.py``）顶层 ``from netops.mcp_server import mcp`` +
``@mcp.tool()`` 直接装饰，**import 域模块即完成注册**。

组合责任在调用方：netops/asgi.py（挂 ``/mcp`` 时）或测试，
``import assets.mcp.tools`` 一行接一个域。

⚠ 防循环硬规矩（与 settings 的防循环规矩同性质）：**本模块禁止 import 任何域工具模块**
——叶子 import 本模块，本模块再 import 叶子即成环。注册清单只许出现在调用方。

本模块导入即建 server，不做任何网络监听；对外服务（Streamable HTTP 挂进
netops.asgi / manage.py stdio）属于传输层接线。
"""

from mcp.server import MCPServer

mcp = MCPServer(
    "netops",
    instructions="网络运维管理平台的 MCP Server。当前提供设备库查询工具（设备、设备组）；所有工具返回结构化 JSON，字符串查询条件留空即不过滤，主机名匹配大小写不敏感。",
)
