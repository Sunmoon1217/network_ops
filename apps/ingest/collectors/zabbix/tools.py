"""Zabbix 采集工具：统一走 zabbix_utils 的动态方法。

``await zapi.<object>.get(**params)``（hostgroup / host / item / history / trigger /
problem），返回的是 JSON-RPC ``result`` 的**裸 dict / list**，不是带属性的对象；
"""

from asyncio import create_task, gather
from datetime import datetime
from logging import getLogger

from core.tools import create_dict_combinations

from .models import ZAPIHistory, ZAPIHost, ZAPIItem, ZAPIProblem, ZAPITrigger
from .zabbix import get_zapi

logger = getLogger(__name__)


async def fetch_groupids(group: str) -> list:
    """
    获取主机组ID列表

    Args:
        zapi (AsyncZabbixAPI): Zabbix API 客户端实例
        group (str): 主机组名称
    Returns:
        return(list): 主机组ID列表
    Raises:
        Exception: 异常
    Examples:
        >>> fetch_groupids()
        ['120','210']
    """
    try:
        zapi = await get_zapi()
        result = await zapi.hostgroup.get(search={"name": group}, output=["groupid"])
        return [item["groupid"] for item in result]
    except Exception as e:
        logger.error(f"获取主机组ID失败: {e}")
        raise


async def fetch_hostids(host: str) -> list:
    """获取主机ID列表

    Args:
        zapi (AsyncZabbixAPI): Zabbix API 客户端实例
        host (str): 主机名称
    Returns:
        list: 主机ID列表
    """
    try:
        zapi = await get_zapi()
        result = await zapi.host.get(search={"name": host}, output=["hostid"])
        return [item["hostid"] for item in result]
    except Exception as e:
        logger.error(f"获取主机ID失败: {e}")
        raise


async def fetch_devicecount(group: str | None = None, groupids: list | None = None) -> int:
    """
    获取设备总数

    :param zapi: Zabbix API 客户端实例
    :param group: 主机组名称
    :param groupids: 主机组ID列表
    :return: 设备总数
    """
    if not groupids and not group:
        logger.warning("未提供主机组名称或ID，无法获取设备总数")
        return 0
    if groupids is None and group:
        groupids = await fetch_groupids(group)

    try:
        zapi = await get_zapi()
        # countOutput 在 Zabbix 5+ 返回字符串，库原样透传 result，需显式转 int
        result = await zapi.host.get(groupids=groupids, countOutput=1)
        return int(result)
    except Exception as e:
        logger.error(f"获取设备总数失败: {e}")
        return 0


async def fetch_items(
    **kwargs,
) -> list[ZAPIItem]:
    """_summary_

    Args:
        zapi (AsyncZabbixAPI): api 实例
        other (Any|None): 其他参数, 已有output / selectHosts
    Returns:
        list[ZAPIItem]: _description_
    """
    kwargs.pop("output", None)
    kwargs.pop("selectHosts", None)
    kwargs.pop("selectHost", None)

    try:
        zapi = await get_zapi()
        result = await zapi.item.get(
            output=["itemid", "name", "key_", "lastvalue", "lastclock"],
            selectHosts=["hostid", "host", "name"],
            **kwargs,
        )
        return [ZAPIItem.model_validate(item) for item in result]
    except Exception as e:
        logger.error(f"获取性能数据项失败: {e}")
        raise


async def fetch_performance_data(
    group: str | None = None,
    groupids: list | None = None,
    name: list[list[str]] | None = None,
    key_: list[str] | None = None,
):
    """
    获取性能数据
    :param zapi: Zabbix API 客户端实例
    :param group: 主机组名称
    :param groupids: 主机组ID列表
    :return: 性能数据列表
    """
    if not groupids and not group:
        logger.warning("未提供主机组名称或ID，无法获取性能数据")
        raise ValueError("未提供主机组名称或ID，无法获取性能数据")
    if groupids is None and group:
        groupids = await fetch_groupids(group)

    if not name and not key_:
        raise ValueError("缺少监控项名称或者key_")
    if not name:
        name = []
    if not key_:
        key_ = []

    try:
        search_list = create_dict_combinations(name=name, key_=key_)
        task_list = [create_task(fetch_items(groupids=groupids, search=search)) for search in search_list]
        results = await gather(*task_list, return_exceptions=True)
        result = [i for item in results if not isinstance(item, BaseException) for i in item]
        return result
    except Exception as e:
        logger.error(f"获取性能数据失败: {e}")
        raise


async def fetch_history_data(
    itemid: str | list[str],
    history_type: int = 0,
    limit: int = 180,
    time_from: str | int | None = None,
    time_till: str | int | None = None,
) -> list[ZAPIHistory]:
    """
    获取历史数据

    Args:
        zapi: Zabbix API 客户端实例
        itemid: 性能数据项ID
        history_type: 历史数据类型（0-数值型，1-字符串型，2-日志型，3-文本型）
        limit: 获取数据的数量限制
    Returns:
        历史数据列表
    """
    params: dict = {"itemids": itemid, "history": history_type, "output": "extend", "limit": limit}
    if time_from:
        params["time_from"] = time_from
    if time_till:
        params["time_till"] = time_till

    try:
        zapi = await get_zapi()
        result = await zapi.history.get(**params)
        return [ZAPIHistory.model_validate(history) for history in result]
    except Exception as e:
        logger.error(f"获取历史数据失败: {e}")
        raise


async def fetch_triggers(triggerid: str | int):
    """
    获取触发器列表
    :param zapi: Zabbix API 客户端实例
    :param triggerid: 触发器ID
    :return: 触发器列表
    """
    try:
        zapi = await get_zapi()
        result = await zapi.trigger.get(
            triggerids=triggerid,
            selectHosts=["hostid", "host", "name"],
            output=["triggerid", "name", "opdata", "priority"],
        )
        if not result:
            logger.warning(f"未找到触发器ID {triggerid} 的信息")
            raise ValueError(f"未找到触发器ID {triggerid} 的信息")
        trigger = result[0]
        host = trigger["hosts"][0]
        return ZAPITrigger.model_validate(trigger), ZAPIHost.model_validate(host)
    except Exception as e:
        logger.error(f"获取触发器列表失败: {e}")
        raise


async def fetch_problems(
    **kwargs,
):
    """
    获取问题列表
    :param zapi: Zabbix API 客户端实例
    :param group: 主机组名称
    :param groupids: 主机组ID列表
    :return: 问题列表
    """
    if not kwargs.get("groupids") and not kwargs.get("group"):
        logger.warning("未提供主机组名称或ID，无法获取问题列表")
        raise ValueError("未提供主机组名称或ID，无法获取问题列表")
    if kwargs.get("groupids") is None and kwargs.get("group"):
        kwargs["groupids"] = await fetch_groupids(kwargs["group"])
    if kwargs.get("hostids") is None and kwargs.get("host"):
        kwargs["hostids"] = await fetch_hostids(kwargs["host"])

    try:
        zapi = await get_zapi()
        params = {"output": "extend", "object": 0}
        if kwargs.get("groupids"):
            params["groupids"] = kwargs["groupids"]
        elif kwargs.get("hostids"):
            params["hostids"] = kwargs["hostids"]

        result = await zapi.problem.get(**params)
        problems: list[ZAPIProblem] = []
        for problem in result:
            try:
                trigger, host = await fetch_triggers(problem["objectid"])
                problems.append(ZAPIProblem.model_validate({**problem, "trigger": trigger, "host": host}))
            except Exception as e:
                logger.warning(f"获取触发器信息失败, 问题为: {problem}, 原因为: {e}")
                continue

        return problems
    except Exception as e:
        logger.error(f"获取问题列表失败: {e}")
        raise


async def fetch_linkpoint(
    host: str,
    ifname: str,
    itemids: list | None = None,
) -> tuple[str, list[str | None]]:
    """_summary_

    Args:
        zapi (AsyncZabbixAPI): _description_
        host (str): _description_
        ifname (str): _description_
        itemids (list | None, optional): _description_. Defaults to None.

    Returns:
        tuple[str, list[str]]: 返回最大值和 监控项id列表组成的元组
    """
    items = []
    if itemids:
        items = await fetch_items(itemids=itemids)
    else:
        hostid = await fetch_hostids(host)
        items = await fetch_items(hostids=hostid, search={"name": [ifname, "带宽使用率"]})
    if not items:
        return "", []
    value = str(max([int(item.lastvalue) for item in items if item.lastvalue]))
    items_id = [item.lastvalue for item in items]
    return value, items_id


async def fetch_linkhistory(
    host: str,
    ifname: str,
    time_from: int,
    time_till: int,
    itemids: list[str] | None = None,
):
    items: list[ZAPIItem] = []
    if not itemids:
        hostid = await fetch_hostids(host)
        items = await fetch_items(
            hostids=hostid,
            search={"name": [ifname, "带宽使用率"]},
        )
        itemids = [item.itemid for item in items]

    histories = await fetch_history_data(itemids, time_from=time_from, time_till=time_till)

    if not histories:
        raise ValueError(f"未采集到数据: {host}, {ifname}, 时间: {datetime.fromtimestamp(time_till)}")
    value = max([float(history.value) for history in histories])
    items_id = [item.lastvalue for item in items]
    return round(value, 2), items_id
