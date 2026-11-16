"""薄转发：Zabbix client 与单例已迁 ``core.integrations.providers.zabbix``。

保留这个模块是为了**调用方与测试的 patch 点不动**：``queries.py`` 里 9 处
``await get_zapi()`` 与 ``tests/ingest/test_link_cache.py`` 的
``patch.object(queries, "get_zapi")`` 都按这个名字找符号。

新代码请直接 ``from core.integrations import acquire``（实例归 core 管），或用
``core.integrations.providers.zabbix`` 里的 client；这里只作为兼容层存在，不要再往里加逻辑。
"""

from core.integrations.providers.zabbix import TypedZabbixAPI, close_zapi, get_zapi

__all__ = ["TypedZabbixAPI", "close_zapi", "get_zapi"]
