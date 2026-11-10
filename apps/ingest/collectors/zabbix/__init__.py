"""Zabbix 采集器：客户端单例 + ``<object>_get`` 薄封装（``zabbix.py``）、查询编排（``queries.py``）。"""

from .zabbix import TypedZabbixAPI, close_zapi, get_zapi

__all__ = ["TypedZabbixAPI", "close_zapi", "get_zapi"]
