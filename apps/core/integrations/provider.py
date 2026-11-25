"""外部系统 client 的 provider 协议：core 只认注册键、取用与释放，不认具体系统。

注册方向永远单向（业务域 → core），client 生命周期归实现方。设计见
handbook/design/external-clients.md「Provider 协议」。
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
