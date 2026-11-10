"""LLM 工具子系统（根目录普通 Python 包，**不是** Django app）。

与 ``apps/`` 下各业务域平级、且位于它们之上：MCP 基建、实体注册表、通用工具与出口都在这里，
``core`` 只管用户 / 认证 / 任务。

**import 本包 = 完成整条接线**（组合根在这里）：先 ``assets.register()``（实体与边，边要求
端点先登记），再 ``register_all()``（把 ``TOOLS`` 逐个挂到根 server）。传输层不在这里，
``mcpserver.streamable_http_app()`` 由 ``netops.asgi`` 调用。

必须在 ``django.setup()`` 之后 import（本包会拉各域 models / serializers）。
⚠ 目录名**绝不能**叫 ``mcp/``：会遮蔽 PyPI 的 mcp SDK。模块分工与两条防循环规矩见 docs/llmtools.md
"""

from llmtools.domains import assets
from llmtools.server import build_transport_security, mcpserver
from llmtools.tools import register_all

__all__ = ["build_transport_security", "mcpserver"]

#: 显式两段：先实体与边（边要求端点先登记），再工具
assets.register()
register_all()
