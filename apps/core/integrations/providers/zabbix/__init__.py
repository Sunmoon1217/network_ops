"""Zabbix 集成：client 单例（``client.py``）+ DTO（``schemas.py``）+ provider（本包出口）。

``queries.py``（查询编排）**没有**跟着搬：那是「采集什么、怎么组装」的业务语义，留在
``apps/ingest/collectors/zabbix/``。这里只负责「怎么连、实例归谁管」。
"""

from .client import TypedZabbixAPI, close_zapi, get_zapi
from .provider import ZabbixProvider
from .schemas import ZAPIGroup, ZAPIHistory, ZAPIHost, ZAPIItem, ZAPIProblem, ZAPITrigger

__all__ = [
    "TypedZabbixAPI",
    "ZAPIGroup",
    "ZAPIHistory",
    "ZAPIHost",
    "ZAPIItem",
    "ZAPIProblem",
    "ZAPITrigger",
    "ZabbixProvider",
    "close_zapi",
    "get_zapi",
]
