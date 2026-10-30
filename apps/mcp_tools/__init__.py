"""MCP Server（LLM 客户端入口）。

用法：``from mcp_tools import mcp`` 拿到已注册全部工具的 server 单例，
传输层（ASGI 挂载 / stdio）在此之外接线，见 mcp_tools.server 模块注释。
"""

from mcp_tools.server import mcp

__all__ = ["mcp"]
