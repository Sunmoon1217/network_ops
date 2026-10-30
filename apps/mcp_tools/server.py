"""MCP Server 本体：只负责建 server 与按域注册工具。

工具实现按域拆在 ``mcp_tools.tools.*``，每个模块暴露 ``register(mcp)``——
新域（配置、访问流……）加一个模块、在文件末尾注册一行即可。

注意这里是 Django 项目内的普通模块：导入即建 server 并注册工具，
不做任何网络监听；对外服务（Streamable HTTP 挂进 netops.asgi / manage.py stdio）
属于后续接线，不放在本模块。
"""

from mcp.server import MCPServer

from mcp_tools.tools import devices

mcp = MCPServer(
    "netops",
    instructions="网络运维管理平台的 MCP Server。当前提供设备库查询工具（设备、设备组）；所有工具返回结构化 JSON，字符串查询条件留空即不过滤，主机名匹配大小写不敏感。",
)

devices.register(mcp)
