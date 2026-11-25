"""Zabbix 采集器：查询编排（``queries.py``）+ 兼容转发（``zabbix.py``）。

client 单例与 DTO 已迁 ``core/integrations/providers/zabbix/``（实例归 core 统管，见
``handbook/integrations.md``）；本包只剩「查什么、怎么组装」的业务语义。
"""

from .client import TypedZabbixAPI, close_zapi, get_zapi

__all__ = ["TypedZabbixAPI", "close_zapi", "get_zapi"]
