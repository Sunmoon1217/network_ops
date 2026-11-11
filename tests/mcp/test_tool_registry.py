"""工具清单对账：注册到根 server 的工具集合必须与声明的清单一致。

工具名是**全局平面命名空间**，LLM 侧只认名字：改名、漏注册（忘了在 ``llmtools.tools`` 的
``TOOLS`` 里加一行）、撞名都会静默改变对外能力面。撞名在 ``register_all()`` 里已经是启动期
硬错（``RuntimeError``），所以本文件守的是另外两件事：

- **快照漂移**：新增 / 删除工具必须显式改快照（review 时看得见，也提醒同步 handbook）；
- **包装丢签名**：``with_db_lifecycle`` 去掉 ``functools.wraps`` 之后入参 schema 会变成空对象，
  LLM 就不知道该怎么调——这个错误在启动期完全不报。
"""

import asyncio

import llmtools  # noqa: F401 — 包初始化即接线（注册实体 + 工具）
from llmtools import mcpserver
from llmtools.tools import TOOLS

#: 当前对外暴露的全部工具。改这里 = 改 LLM 的能力面，review 必须看得见。
EXPECTED_TOOLS = {"find", "list_records", "query", "get_record", "bundle", "relations", "locate"}


def _tools():
    return asyncio.run(mcpserver.list_tools())


def test_registered_tools_match_manifest():
    assert {tool.name for tool in _tools()} == EXPECTED_TOOLS


def test_manifest_has_no_duplicates():
    names = [fn.__name__ for fn in TOOLS]
    assert len(names) == len(set(names))
    assert len(TOOLS) == len(EXPECTED_TOOLS)


def test_every_tool_is_documented_and_typed():
    for tool in _tools():
        assert tool.description, f"{tool.name} 缺 docstring（LLM 只能靠它理解工具）"
        assert tool.input_schema.get("properties"), f"{tool.name} 入参 schema 为空（检查 functools.wraps 是否保留签名）"
