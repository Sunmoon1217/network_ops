"""各业务域的 MCP 接入（llmtools 里唯一 import 业务域的地方）。

一个域一个包，契约只有两样：

- ``register()``：登记该域的 ``EntitySpec`` / ``Edge``（幂等）
- ``TOOLS``：该域贡献给 LLM 的工具函数（纯函数，不带 ``@mcp.tool()``）

新增域 = 建 ``llmtools/domains/<域>/``（``specs.py`` + ``tools.py`` + ``__init__`` 暴露契约），
再在 ``llmtools/__init__.py`` 加一行 import + 一行 ``register()``，并在 ``llmtools/tools.py``
的 ``TOOLS`` 里加 ``*<域>.TOOLS``。

依赖方向是**单向**的：``llmtools → apps``。各域不再认识 MCP——它们只提供模型、序列化器
与业务函数，谁暴露、暴露多少由这里决定（暴露面审查只需要看 ``llmtools/``）。
"""
