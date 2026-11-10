"""MCP 工具注册表：**唯一注册点**。

工具**实现**分两处：通用工具在 ``llmtools.entity_tools``（只认注册表、不认具体域），
域专属工具在 ``llmtools.domains.<域>.tools``（只知道本域业务）。本模块只做三件事：
汇总名单 → 统一套执行包装 → 一次性挂到根 server 上。

为什么集中注册，而不是各域 ``@mcp.tool()`` 自装饰：

- 工具名是给 LLM 的公开接口面，**重名在启动时暴露**（SDK 默认是静默覆盖后者），
  比运行时才发现「我调了 A 却进了 B」好得多；
- ``with_db_lifecycle`` 这类横切执行语义一处套上，新增工具漏不掉；
- 域模块不再依赖 ``llmtools.server``，只剩纯函数（+ SDK 的 ``ToolError``），
  单测可以直接调函数，不必先建 server。

新增工具：在实现模块里写普通函数（**保留 docstring**——它是 LLM 看到的说明书，
参数名与类型注解决定入参 schema），然后加进下面的 ``TOOLS``（域工具通过
``llmtools.domains.<域>.TOOLS`` 聚合）。**不要**再给函数加 ``@mcp.tool()``。
"""

from collections.abc import Callable
from typing import Any

from llmtools import entity_tools
from llmtools.domains import assets
from llmtools.server import mcpserver, with_db_lifecycle

#: 对外暴露的工具名单（顺序即 ``list_tools`` 的返回顺序）
TOOLS: tuple[Callable[..., Any], ...] = (
    entity_tools.find,
    entity_tools.list_records,
    entity_tools.query,
    entity_tools.get_record,
    entity_tools.bundle,
    entity_tools.relations,
    *assets.TOOLS,
)

_registered = False


def register_all() -> None:
    """把 ``TOOLS`` 挂到根 server（幂等：重复调用是空操作）。

    重名与工具函数本身的模块归属在这里先校验一遍再注册——启动期炸掉，好过
    LLM 侧静默拿到一个被覆盖的工具。
    """
    global _registered
    if _registered:
        return

    owners: dict[str, str] = {}
    for fn in TOOLS:
        name = fn.__name__
        if name in owners:
            raise RuntimeError(f"工具重名：{name}（{owners[name]} 与 {fn.__module__}）——LLM 侧只会看到后注册的那个")
        owners[name] = fn.__module__

    for fn in TOOLS:
        mcpserver.add_tool(with_db_lifecycle(fn))
    _registered = True
