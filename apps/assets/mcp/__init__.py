"""assets 域的 MCP 接入：实体声明在 ``specs``，域专属工具在 ``tools``。

import 本包即完成「通用工具注册 + 资产实体注册」；``locate`` 仍要显式
``import assets.mcp.tools``（组合方与测试都这么做）。
"""

import assets.mcp.specs  # noqa: F401 — 资产实体与边注册
import core.mcp.tools  # noqa: F401 — 通用工具注册
