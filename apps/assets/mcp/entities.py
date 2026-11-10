"""兼容壳：通用注册表已迁到 ``core.mcp.registry``，资产 spec 见 ``assets.mcp.specs``。

保留本文件只为旧 import 不断（``from assets.mcp.entities import SPEC / get_spec``）；
新代码请直接 ``from core.mcp.registry import ...``。
"""

from assets.mcp.specs import EDGES, SPEC, NodeType  # noqa: F401
from core.mcp.registry import *  # noqa: F401,F403
from core.mcp.registry import __all__ as _registry_all

__all__ = [*_registry_all, "EDGES", "SPEC", "NodeType"]
