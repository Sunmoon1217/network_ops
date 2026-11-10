"""LLM 工具子系统（根目录普通 Python 包，**不是** Django app）。

与 ``apps/`` 下各业务域平级、且位于它们之上：MCP 的基建、实体注册表、通用工具与出口
全在这里，``core`` 只管用户 / 认证 / 任务。

| 模块 | 职责 |
|------|------|
| ``llmtools.server`` | 根 server 单例 ``mcpserver`` + ``with_db_lifecycle`` + ``build_transport_security`` |
| ``llmtools.registry`` | 实体注册表 ``SPEC`` / ``EDGES``：各域把可查的模型或视图登记进来 |
| ``llmtools.query`` | QueryPlan 编译器（受控 AND/OR / 排序 / 投影 / offset） |
| ``llmtools.entity_tools`` | 通用工具实现（find / list_records / query / get_record / bundle / relations），纯函数 |
| ``llmtools.tools`` | **工具注册表**：汇总各域工具名单 + 统一套 ``with_db_lifecycle`` + ``add_tool()`` |
| ``llmtools.domains.<域>`` | 各域接入：``specs.py`` 实体声明 + ``tools.py`` 纯函数，契约 ``register()`` / ``TOOLS`` |

**import 本包 = 完成整条接线**（组合根就在这里）：

1. ``assets.register()`` —— 登记实体与边
2. ``register_all()`` —— 把 ``TOOLS`` 逐个挂到根 server

传输层**不在这里**：``mcpserver.streamable_http_app()`` 由 ``netops.asgi`` 调用——本包不认识
Django，也不决定站点怎么装配。对外只暴露 ``mcpserver`` 与 ``build_transport_security``。

⚠ 本包会拉各域 models / serializers，必须在 ``django.setup()`` 之后 import；因此
``from llmtools.registry import SPEC`` 这类子模块导入也会连带初始化整条链路。
⚠ 目录名**绝不能**叫 ``mcp/``：项目根在 ``sys.path`` 最前，会遮蔽 PyPI 的 mcp SDK
（``from mcp.server import MCPServer`` 会变成 ``ModuleNotFoundError: No module named 'mcp.server'``）。
"""

from llmtools.domains import assets
from llmtools.server import build_transport_security, mcpserver
from llmtools.tools import register_all

__all__ = ["build_transport_security", "mcpserver"]

#: 显式两段：先实体与边（边要求端点先登记），再工具
assets.register()
register_all()
