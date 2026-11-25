"""外部连接实例与 client 生命周期（core 的第三块平台职责）。

三块职责并列：用户 / 认证 / 权限、任务机制（``core/tasks.py``）、外部连接实例（本包）。

**取用方式**：

.. code-block:: python

    from core.integrations import acquire

    zapi = await acquire("zabbix")          # 异步 client（Zabbix / autotask）
    client = acquire_sync("dify")           # 同步 client（provider 需实现 acquire_sync）

**注册方式**（业务域在 ``AppConfig.ready()`` 里，方向永远是 域 → core）：

.. code-block:: python

    from core.integrations import register_provider
    from core.integrations.providers.zabbix import ZabbixProvider

    register_provider(ZabbixProvider())

**释放**：ASGI 走 ``netops.asgi`` 的 lifespan 钩子，Celery 走 worker 子进程的
``worker_process_shutdown``——两者都只调 ``release_all()``。

现状文档见 ``handbook/integrations.md``；设计取向见
``handbook/design/external-clients.md``。
"""

from .provider import Provider
from .registry import (
    DEFAULT_INSTANCE,
    acquire,
    acquire_sync,
    describe_all,
    get_provider,
    register_provider,
    registered,
    release_all,
)

__all__ = [
    "DEFAULT_INSTANCE",
    "Provider",
    "acquire",
    "acquire_sync",
    "describe_all",
    "get_provider",
    "register_provider",
    "registered",
    "release_all",
]
