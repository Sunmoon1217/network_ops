"""Zabbix JSON-RPC ``get`` 结果的 DTO。

字段口径与 ``zabbix.py`` 里各 ``<object>_get`` 固化的 ``output`` / ``selectHosts``
对齐：请求过的字段在这里声明，其余字段由 ``netops.schema.ExtraModel`` 的
``extra="allow"`` 兜底（Zabbix 各版本返回的字段不完全一致，不逐项列全）。
改固化参数时要同步改这里。

ID / 时间戳 / 优先级 / 严重级别在 JSON-RPC 里都是**字符串**，不做隐式数值转换；
``item.get`` / ``trigger.get`` 的 ``selectHosts`` 结果直接声明成 ``list[ZAPIHost]``，
由 pydantic 完成嵌套实例化，查询层不必再手工 ``model_validate``。
"""

from netops.schema import ExtraModel


class ZAPIGroup(ExtraModel):
    """``hostgroup.get`` 结果。"""

    groupid: str
    name: str | None = None


class ZAPIHost(ExtraModel):
    """``host.get`` 结果，也是 item / trigger 的 ``selectHosts`` 元素。"""

    hostid: str
    host: str | None = None
    name: str | None = None


class ZAPIItem(ExtraModel):
    """``item.get`` 结果：output 固化 5 字段 + selectHosts 3 字段。"""

    itemid: str
    name: str | None = None
    key_: str | None = None
    lastvalue: str | None = None
    lastclock: str | None = None
    hosts: list[ZAPIHost] = []


class ZAPITrigger(ExtraModel):
    """``trigger.get`` 结果：output 固化 4 字段 + selectHosts。"""

    triggerid: str
    name: str | None = None
    opdata: str | None = None
    priority: str | None = None
    hosts: list[ZAPIHost] = []


class ZAPIProblem(ExtraModel):
    """``problem.get`` 结果；``host`` / ``trigger`` 由查询层关联后补齐。"""

    eventid: str
    objectid: str
    clock: str | None = None
    name: str | None = None
    severity: str | None = None
    acknowledged: str | None = None
    host: ZAPIHost | None = None
    trigger: ZAPITrigger | None = None


class ZAPIHistory(ExtraModel):
    """``history.get`` 结果；``output=extend`` 还可能带 ns 等版本相关字段。"""

    itemid: str
    clock: str
    value: str
    ns: str | None = None
