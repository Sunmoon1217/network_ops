"""MCP 基建（core 域）：根 server + 实体注册表 + 结构化查询编译器 + 通用工具。

**边界**：本子包是「查询基建」，不读 core 的业务数据——禁止 import
``core.models`` / ``core.api`` / ``core.permissions`` / ``core.tasks``；
同样禁止 import 任何域模块（``assets`` / ``analysis`` / ``docs`` …）。
域通过 ``register_entity`` / ``register_edge`` 把模型或视图登记进来，
由组合方（``netops.asgi`` 或测试）import 域模块触发注册。

import 本包即建 server，不做网络监听；工具要显式 import ``core.mcp.tools``
才会注册（与「import 域模块即注册」的约定一致）。
"""

from core.mcp.registry import (
    EDGES,
    MAX_DEPTH,
    MAX_PAGE_SIZE,
    SPEC,
    Edge,
    EntitySpec,
    Filter,
    clear_registry,
    get_spec,
    register_edge,
    register_entity,
    unregister_entity,
)
from core.mcp.server import build_transport_security, mcp, with_db_lifecycle

__all__ = [
    "EDGES",
    "MAX_DEPTH",
    "MAX_PAGE_SIZE",
    "SPEC",
    "Edge",
    "EntitySpec",
    "Filter",
    "build_transport_security",
    "clear_registry",
    "get_spec",
    "mcp",
    "register_edge",
    "register_entity",
    "unregister_entity",
    "with_db_lifecycle",
]
