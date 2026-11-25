"""兼容薄转发：client 与单例已迁 ``core.integrations.providers.zabbix``。

保留模块只为调用方与测试的 patch 点不动；新代码用 ``core.integrations.acquire("zabbix")``，
不要再往里加逻辑。
"""

from core.integrations.providers.zabbix import TypedZabbixAPI, close_zapi, get_zapi

__all__ = ["TypedZabbixAPI", "close_zapi", "get_zapi"]
