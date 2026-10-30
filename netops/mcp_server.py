"""MCP Server 装配点（与 netops.urls 同性质：只接线、零业务逻辑）。

建 server 单例 + 逐域注册工具：工具实现按域住在 ``apps/<app>/mcp/``（与各域的
``api/`` 同构），每个域暴露 ``register(mcp)``——新域（配置 ingest、关系与分析
analysis……）加一行 import + 一行 register 即可，依赖方向由包结构天然约束
（analysis.mcp 可以 import ingest/assets，反过来不行）。

注意这里是 Django 项目内的普通模块：导入即建 server 并注册工具，
不做任何网络监听；对外服务（Streamable HTTP 挂进 netops.asgi / manage.py stdio）
属于传输层接线，不放在本模块。
"""

from mcp.server import MCPServer

from assets.mcp import register as register_assets

mcp = MCPServer(
    "netops",
    instructions="网络运维管理平台的 MCP Server。当前提供设备库查询工具（设备、设备组）；所有工具返回结构化 JSON，字符串查询条件留空即不过滤，主机名匹配大小写不敏感。",
)

register_assets(mcp)
