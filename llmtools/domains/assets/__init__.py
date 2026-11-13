"""资产域接入：设备 / 设备组 / 接口 / VLAN / VRF / 路由 / 网段 / IP / ARP / 负载均衡 /
防火墙策略族 / 服务器负责人，外加 ``locate`` 工具。

``nodes.py`` 是节点类型常量，``specs/`` 是实体声明（26 类 ``EntitySpec``，按子域分文件），
``edges.py`` 是关系边（36 条，独立一层），``tools`` 是必须知道资产域业务语义的工具实现。
这些都是纯声明与纯函数，注册动作由 ``llmtools/__init__.py``（接线）与
``llmtools.tools``（注册）统一发起。
"""

from . import specs, tools

#: 本域贡献给 LLM 的工具（纯函数；包装与注册由 llmtools.tools 统一负责）
TOOLS = (tools.locate,)


def register() -> None:
    """登记本域实体与边（幂等，由 ``llmtools.boot`` 调用）。"""
    specs.register()


__all__ = ["TOOLS", "register", "specs", "tools"]
