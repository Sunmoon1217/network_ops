from asyncio import CancelledError, Task, create_task, gather
from datetime import datetime, timedelta
from logging import getLogger
from typing import Any

from .queries import ZAPIItem, device_count, items, problems
from .schemas import ZAPIProblem
from .zabbix import AsyncZabbixAPI

logger = getLogger(__name__)

PANEL = ["statusbar", "devicestatus", "link", "slb", "inspection", "itsmtask"]
GROUP = [
    "devicecount",
    "healthy",
    "switch...",
]
NAME = ["count"]

group_dict = {
    "交换机": "switch",
    "路由器": "router",
    "防火墙": "firewall",
    "负载均衡": "loadbalance",
    "DNS": "dns",
}


link_dict = {
    "ipv4": {
        "zjbgp": {"host": "ZGCB-ZJE04-INT-AS01", "ifname": "ifname", "itemids": []},
        "jxqcu": {"host": "ZGCB-JXQA03-INT-AS01", "ifname": "ifname", "itemids": []},
        "jxqlct": {"host": "ZGCB-JXQA03-INT-AS01", "ifname": "ifname", "itemids": []},
    },
    "ipv6": {
        "zjbgp": {"host": "ZGCB-ZJE04-INT-AS01", "ifname": "ifname", "itemids": []},
        "jxqcu": {"host": "ZGCB-JXQA03-INT-AS01", "ifname": "ifname", "itemids": []},
        "jxqct": {"host": "ZGCB-JXQA03-INT-AS01", "ifname": "ifname", "itemids": []},
    },
    "fwlink": {
        "coreyw": {"host": "ZGCB-ZJB02-COREYW-FW01", "ifname": "ifname", "itemids": []},
        "intyw": {"host": "ZGCB-ZJB02-INTYW-FW01", "ifname": "ifname", "itemids": []},
        "mgtyw": {"host": "ZGCB-ZJB02-MGTYW-FW01", "ifname": "ifname", "itemids": []},
        "intdmz": {"host": "ZGCB-ZJE04-INT-FW01", "ifname": "ifname", "itemids": []},
    },
}


def aligned_now():
    """获取当前时间向前对齐整3分钟的时间点

    Returns:
        datetime: 一个过去最近的整3分钟的时间点
    """
    now = datetime.now()
    minutes = now.minute
    remainder = minutes % 3
    time = now.replace(second=0, microsecond=0)
    time -= timedelta(minutes=remainder)
    return time


def get_timeaxis(time_start: str | None = None):
    """获取时间轴, 包含过去3个小时, 每个整3分钟的时间和时间戳

    Returns:
        dict: 返回一个字典, key为时间, value为时间戳
    """
    aligned_end = aligned_now()
    if not time_start:
        aligned_start = aligned_end - timedelta(hours=3)
    else:
        _time = datetime.strptime(time_start, "%H:%M").time()
        now = datetime.now()
        _date = now.date()
        if _time > now.time():
            _date = _date - timedelta(days=1)
        aligned_start = datetime.combine(_date, _time)
        mod180 = aligned_start.timestamp() % 180
        if mod180 != 0:
            aligned_start = datetime.fromtimestamp(aligned_start.timestamp() // 180 * 180)

    time_axis: list[datetime] = []
    current_time = aligned_end
    step = timedelta(minutes=3)

    while current_time >= aligned_start:
        time_axis.append(current_time)
        current_time -= step

    time_axis.sort()

    formatted_times = {t.strftime("%H:%M"): int(t.timestamp()) for t in time_axis}
    return formatted_times


async def update_devicecount(zapi: AsyncZabbixAPI, group_dict: dict[str, str]):
    logger.info("定时任务开始: 采集/更新 设备数量信息")
    tasks: list[Task[int]] = []
    for group in group_dict.keys():
        tasks.append(create_task(device_count(group)))
    try:
        results = await gather(*tasks, return_exceptions=True)
        return results
    except CancelledError:
        pass

    ## 保存数据库
    # async with AsyncSession() as s:
    #     total = 0
    #     for i, res in enumerate(results):
    #         group = list(group_dict.values())[i]
    #         if isinstance(res, BaseException):
    #             logger.error(f"设备数量采集失败, 设备类型为: {group}, 失败原因为: {res}")
    #             continue
    #         total += res
    #         try:
    #             dashboard = DashboardData(
    #                 panel="devicestatus",
    #                 group=group,
    #                 name="count",
    #                 value=res,
    #                 list_value=None,
    #             )

    #             await s.merge(dashboard)
    #             logger.debug(f"更新{group}设备数量: {res}")
    #         except Exception as e:
    #             logger.error(f"更新数据库设备数量失败, 设备类型为: {group}, 失败原因为: {e}")
    #             continue

    #     try:
    #         dashboard = DashboardData(
    #             panel="statusbar",
    #             group="devicecount",
    #             name="count",
    #             value=None,
    #             list_value=[{"count": total}],
    #         )

    #         await s.merge(dashboard)
    #         logger.debug(f"更新{group}设备数量: {res}")
    #     except Exception as e:
    #         logger.error(f"更新数据库设备数量失败, 设备类型为: {group}, 失败原因为: {e}")

    #     await s.commit()


async def update_deviceproblem(zapi: AsyncZabbixAPI, group_dict: dict[str, str]):
    logger.info("定时任务开始: 采集/更新 告警信息")
    tasks: list[Task[list[ZAPIProblem]]] = []
    results: list[list[ZAPIProblem] | BaseException] = []
    for group in group_dict.keys():
        tasks.append(create_task(problems(group)))
    try:
        results = await gather(*tasks, return_exceptions=True)
        return results
    except CancelledError:
        pass

    ## 保存数据库
    # async with AsyncSession() as s:
    #     for i, res in enumerate(results):
    #         group = list(group_dict.values())[i]
    #         if isinstance(res, BaseException):
    #             logger.error(f"设备告警采集失败, 设备类型为: {group}, 失败原因为: {res}")
    #             continue

    #         try:
    #             list_value = [item.model_dump() for item in res]
    #             dashboard = DashboardData(
    #                 panel="devicestatus",
    #                 group=group,
    #                 name="problems",
    #                 value=None,
    #                 list_value=list_value,
    #             )

    #             await s.merge(dashboard)
    #             await s.commit()
    #             logger.debug(f"更新{group}设备告警: {res}")
    #         except Exception as e:
    #             logger.error(f"更新数据库设备告警信息失败, 设备类型为: {group}, 失败原因为: {e}")
    #             continue


async def update_deviceperformance(zapi: AsyncZabbixAPI, group_dict: dict[str, str]):
    logger.info("定时任务开始: 采集/更新 设备性能信息")
    cpukey = ["cpu.util", "cpu.uilition", "topsec.cpu", "cpu.usage"]
    memkey = ["memory.util", "mem.tmm.ratio", "zdns.mem.usage"]

    cpu_tasks: list[Task[list[ZAPIItem]]] = []
    mem_tasks: list[Task[list[ZAPIItem]]] = []
    for group in group_dict.keys():
        cpu_tasks.append(create_task(items(group=group, key_=cpukey)))
        mem_tasks.append(create_task(items(group=group, key_=memkey)))
    try:
        cpu_results = await gather(*cpu_tasks, return_exceptions=True)
        mem_results = await gather(*mem_tasks, return_exceptions=True)
        return cpu_results, mem_results
    except CancelledError:
        pass

    ## 保存数据库
    # async with AsyncSession() as s:
    #     for idx, res in enumerate(cpu_results):
    #         group = list(group_dict.values())[idx]
    #         if isinstance(res, BaseException):
    #             logger.error(f"设备CPU性能采集失败, 设备类型为: {group}, 失败原因为: {res}")
    #             continue

    #         try:
    #             for i in res:
    #                 host = i.hosts[0]["name"]
    #                 performance = DevicePerformance(
    #                     group=group,
    #                     host=host,
    #                     key_=i.key_,
    #                     type_="cpu",
    #                     value=float(i.lastvalue) if i.lastvalue else None,
    #                 )

    #                 await s.merge(performance)
    #                 await s.commit()
    #                 logger.debug(f"更新{host}设备CPU性能: {i.lastvalue}")

    #             stmp_cputop = (
    #                 select(
    #                     DevicePerformance.host,
    #                     func.max(DevicePerformance.value).label("maxvalue"),
    #                 )
    #                 .where(
    #                     DevicePerformance.group == group,
    #                     DevicePerformance.type_ == "cpu",
    #                 )
    #                 .group_by(DevicePerformance.host)
    #                 .order_by(desc("maxvalue"))
    #                 .limit(5)
    #             )
    #             db_cputop = await s.execute(stmp_cputop)
    #             res_db = db_cputop.all()
    #             if not res:
    #                 raise ValueError(f"数据库获取数据失败: {res_db}")
    #             cpumax = max(item.tuple()[1] for item in res_db)
    #             cputop = [{"label": item.tuple()[0], "value": item.tuple()[1]} for item in res_db]
    #             dashboard_cputop = DashboardData(
    #                 panel="devicestatus",
    #                 group=group,
    #                 name="cputop",
    #                 value=None,
    #                 list_value=cputop,
    #             )
    #             dashboard_cpumax = DashboardData(
    #                 panel="devicestatus",
    #                 group=group,
    #                 name="cpumax",
    #                 value=str(cpumax),
    #                 list_value=None,
    #             )
    #             await s.merge(dashboard_cputop)
    #             await s.merge(dashboard_cpumax)
    #             await s.commit()

    #         except Exception as e:
    #             logger.error(f"更新数据库设备CPU性能失败, 设备类型为: {group}, 失败原因为: {e}")
    #             continue

    #     for i, res in enumerate(mem_results):
    #         group = list(group_dict.values())[i]
    #         if isinstance(res, BaseException):
    #             logger.error(f"设备内存性能采集失败, 设备类型为: {group}, 失败原因为: {res}")
    #             continue

    #         try:
    #             for i in res:
    #                 host = i.hosts[0]["name"]
    #                 performance = DevicePerformance(
    #                     group=group,
    #                     host=host,
    #                     key_=i.key_,
    #                     type_="mem",
    #                     value=int(i.lastvalue) if i.lastvalue else None,
    #                 )

    #                 await s.merge(performance)
    #                 await s.commit()
    #                 logger.debug(f"更新{group}设备内存性能: {res}")

    #             stmp_memtop = (
    #                 select(
    #                     DevicePerformance.host,
    #                     func.max(DevicePerformance.value).label("maxvalue"),
    #                 )
    #                 .where(
    #                     DevicePerformance.group == group,
    #                     DevicePerformance.type_ == "mem",
    #                 )
    #                 .group_by(DevicePerformance.host)
    #                 .order_by(desc("maxvalue"))
    #                 .limit(5)
    #             )
    #             db_memtop = await s.execute(stmp_memtop)
    #             res_db = db_memtop.all()
    #             if not res:
    #                 raise ValueError(f"数据库获取数据失败: {res_db}")

    #             memmax = max([int(i[1]) for i in res_db])
    #             memtop = [{"label": host, "value": value} for host, value in res_db]
    #             dashboard_memtop = DashboardData(
    #                 panel="devicestatus",
    #                 group=group,
    #                 name="memtop",
    #                 value=None,
    #                 list_value=memtop,
    #             )
    #             dashboard_memmax = DashboardData(
    #                 panel="devicestatus",
    #                 group=group,
    #                 name="memmax",
    #                 value=str(memmax),
    #                 list_value=None,
    #             )
    #             await s.merge(dashboard_memtop)
    #             await s.merge(dashboard_memmax)
    #             await s.commit()

    #         except Exception as e:
    #             logger.error(f"更新数据库设备内存性能失败, 设备类型为: {group}, 失败原因为: {e}")
    #             continue


## 后面再实现
# async def update_linksummary():
#     async with AsyncSession() as s:
#         dbvalues = await s.scalars(select(DashboardData).where(DashboardData.group == "linechart"))
#         datalist = dbvalues.all()

#         i = 0
#         t = 0
#         for data in datalist:
#             data = ReadDashboard.model_validate(data)
#             if not data.list_value:
#                 continue
#             value = data.list_value[0]
#             if not value:
#                 continue
#             try:
#                 linkobj = LinkObject.model_validate(value)
#                 linkdict = linkobj.model_dump()
#                 for g, d in linkdict.items():
#                     if g == "fwlink":
#                         continue
#                     for v in d.values():
#                         t += 1
#                         if v > 90:
#                             i += 1

#             except ValidationError:
#                 logger.error(f"模型LinkObject 验证数据异常: 数据为{data}")
#                 continue

#         if t:
#             healthy = round(i / t, 2)

#             dashboard_healthy = DashboardData(
#                 panel="statusbar",
#                 group="linkhealthy",
#                 name="healthy",
#                 value=None,
#                 list_value=[{"healthy": healthy, "count": i}],
#             )

#             await s.merge(dashboard_healthy)
#         dashboard_count = DashboardData(
#             panel="statusbar",
#             group="linkhealthy",
#             name="count",
#             value=str(i),
#             list_value=None,
#         )
#         dashboard_int = DashboardData(
#             panel="link",
#             group="statistic",
#             name="internet",
#             value=None,
#             list_value=[{"count": "6", "stable": "100%", "risk": "0"}],
#         )
#         dashboard_ext = DashboardData(
#             panel="link",
#             group="statistic",
#             name="ext",
#             value=None,
#             list_value=[{"count": "47", "stable": "100%", "risk": "0"}],
#         )
#         dashboard_wan = DashboardData(
#             panel="link",
#             group="statistic",
#             name="wan",
#             value=None,
#             list_value=[{"count": "4", "stable": "100%", "risk": "0"}],
#         )
#         await s.merge(dashboard_count)
#         await s.merge(dashboard_int)
#         await s.merge(dashboard_ext)
#         await s.merge(dashboard_wan)
#         await s.commit()


async def update_linkhistory(zapi: AsyncZabbixAPI, link_dict: dict[str, dict[str, dict[str, str]]]):
    logger.info("定时任务开始: 采集/更新 链路信息")

    timeaxis = get_timeaxis()
    namelist = [f"bandwidth-{label}" for label in timeaxis.keys()]

    ## 检查当前数据
    # async with AsyncSession() as s:
    #     await s.execute(
    #         delete(DashboardData).where(
    #             DashboardData.panel == "link",
    #             DashboardData.group == "linechart",
    #             DashboardData.name.not_in(namelist),
    #         )
    #     )
    #     await s.commit()
    #     dbvalues = await s.scalar(select(DashboardData).where(DashboardData.name.contains("bandwidth")).order_by(DashboardData.update_at.asc()).limit(1))

    zonelist = []
    if dbvalues:
        time_label = dbvalues.name.split("_")[1]
        zonelist = list(get_timeaxis(time_label).items())
    else:
        zonelist = list(get_timeaxis().items())

    if not zonelist or len(zonelist) == 1:
        return
    for i in range(len(zonelist) - 1):
        zone = (zonelist[i], zonelist[i + 1])
        await update_linkpoint(zapi, link_dict, timerange=zone)


async def update_linkall(zapi: AsyncZabbixAPI, link_dict: dict[str, dict[str, dict[str, Any]]]):
    tasks: list[Task[tuple[str, list[str]]]] = []
    task_name: list[str] = []

    time = get_timeaxis()
    for group, link in link_dict.items():
        for name, ifinfo in link.items():
            tasks.append(create_task(fetch_linkpoint(zapi, **ifinfo)))
            task_name.append(f"{group}_{name}")
    try:
        results = await gather(*tasks, return_exceptions=True)
    except CancelledError:
        pass

    async with AsyncSession() as s:
        name = f"bandwidth-{time}"
        data = {"time": time, "data": {}}
        for i, res in enumerate(results):
            name = task_name[i]
            if isinstance(res, BaseException):
                logger.error(f"链路使用率采集失败, 链路名称: {name}, 失败原因为: {res}")
                value = "0"
                itemids = []
            else:
                value = res[0]
                itemids = res[1]

            group, name = name.split("_")
            link_dict[group][name]["itemids"] = itemids
            if group not in data:
                data[group] = {}
            data["data"][group][name] = value

            try:
                dashboard = DashboardData(
                    panel="link",
                    group="linechart",
                    name=f"bandwidth_{time}",
                    value=value,
                    list_value=None,
                )

                await s.merge(dashboard)
                await s.commit()
                logger.debug(f"更新{group}链路使用率: {res}")
            except Exception as e:
                logger.error(f"更新数据库链路使用率失败, 设备类型为: {group}, 失败原因为: {e}")
                continue


async def update_linkpoint(
    zapi: AsyncZabbixAPI,
    link_dict: dict[str, dict[str, dict[str, Any]]],
    timerange: tuple[tuple[str, int], tuple[str, int]],
):
    tasks: list[Task[tuple[str, list[str]]]] = []
    task_name: list[str] = []

    start, end = timerange
    time = end[0]
    time_from = start[1]
    time_till = end[1]
    for group, link in link_dict.items():
        for name, ifinfo in link.items():
            tasks.append(create_task(fetch_linkhistory(zapi, **ifinfo, time_from=time_from, time_till=time_till)))
            task_name.append(f"{group}_{name}")
    try:
        results = await gather(*tasks, return_exceptions=True)
    except CancelledError:
        pass

    async with AsyncSession() as s:
        name = f"bandwidth-{time}"
        data = {"time": time, "data": {}}
        for i, res in enumerate(results):
            name = task_name[i]
            if isinstance(res, BaseException):
                logger.error(f"链路使用率采集失败, 链路名称: {name}, 失败原因为: {res}")
                value = "0"
                itemids = []
            else:
                value = res[0]
                itemids = res[1]

            group, name = name.split("_")
            link_dict[group][name]["itemids"] = itemids
            if group not in data["data"]:
                data[group] = {}
            data["data"][group][name] = value

        try:
            dashboard = DashboardData(
                panel="link",
                group="linechart",
                name=f"bandwidth_{time}",
                value=None,
                list_value=[data],
            )

            await s.merge(dashboard)
            await s.commit()
            logger.debug(f"更新{group}链路使用率: {res}")
        except Exception as e:
            logger.error(f"更新数据库链路使用率失败, 设备类型为: {group}, 失败原因为: {e}")
