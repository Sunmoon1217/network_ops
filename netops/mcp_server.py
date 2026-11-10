"""兼容壳：MCP 基建已迁到 ``core.mcp``（真源见 ``apps/core/mcp/server.py``）。

保留本文件只为旧 import 不断（``netops/asgi.py`` 与测试曾从这里取 ``mcp``）；
新代码请用 ``from core.mcp import mcp``。
"""

from core.mcp.server import build_transport_security, mcp, with_db_lifecycle

__all__ = ["build_transport_security", "mcp", "with_db_lifecycle"]
