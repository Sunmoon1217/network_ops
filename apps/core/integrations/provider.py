"""外部系统 client 的 provider 协议：core 只认这三样，不认具体系统。

设计取向见 ``handbook/design/external-clients.md``「Provider 协议」：

- **注册方向单向**：各域在 ``AppConfig.ready()`` 里 ``register_provider(...)``，core 只按
  ``(system, instance)`` 查表，绝不 import 业务域；
- **生命周期归 provider**：懒建、复用、释放都由实现方决定。Zabbix 的事件循环亲和检查就
  属于 provider（``core/integrations/providers/zabbix/provider.py``）——core 不懂
  ``asyncio`` 的 loop，只负责「取实例」「释放」两个动作；
- **同步 client 不硬塞 async**：``acquire`` / ``release`` 是 async 入口，同步实现（Dify /
  阿里云这类每次都新建的）在内部直接返回即可；同步栈取用见 ``registry.acquire_sync``。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Provider(Protocol):
    """一个外部系统在某个实例上的 client 持有者。"""

    #: 系统标识（``zabbix`` / ``aliyun`` / ``dify`` …），与 ``instance`` 组成注册键
    system: str
    #: 实例名（``default`` / ``prod`` / ``test`` …）；多实例能力留给 T16 的状态对账
    instance: str

    async def acquire(self) -> Any:
        """取 client 实例（懒建 / 复用由实现方决定）。"""

    async def release(self) -> None:
        """释放底层资源（登出 / 关 session）。**必须幂等**：进程收尾可能重复调用。"""

    def describe(self) -> dict[str, Any]:
        """自描述：至少含 ``system`` / ``instance`` / 是否已配置。

        core 只把它原样序列化给未来的只读接口，不解释字段含义——否则 core 又要认识
        「url」「token」这些业务词汇。
        """
