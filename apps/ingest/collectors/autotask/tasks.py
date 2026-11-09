from logging import getLogger

from .autotask import fetch_case, fetch_inspect

logger = getLogger(__name__)


async def update_itsmtask():
    logger.info("定时任务开始: 采集/更新 工单信息")
    try:
        response = await fetch_case()
    except Exception:
        return None

    async with AsyncSession() as s:
        count = len(response)
        success = float(100.0)
        dashboard_statusbar = DashboardData(
            panel="statusbar",
            group="itsmtask",
            name="count",
            value=None,
            list_value=[{"count": count, "success": success}],
        )
        await s.merge(dashboard_statusbar)

        for res in response:
            try:
                dashboard = DashboardData(
                    panel="itsmtask",
                    group="case",
                    name=str(res.case_no),
                    value=None,
                    list_value=[res.model_dump()],
                )

                await s.merge(dashboard)

                logger.debug(f"更新工单: {res}")
            except Exception as e:
                logger.error(f"更新数据库工单信息失败, 工单信息为: {res} 失败原因为: {e}")
                continue

            await s.commit()


async def update_aliyunslb():
    logger.info("定时任务开始: 采集/更新 SLB信息")
    res = []
    try:
        res = await fetch_inspect()
    except Exception:
        return None

    async with AsyncSession() as s:
        try:
            dashboard = DashboardData(
                panel="slb",
                group="slb",
                name="slb",
                value=None,
                list_value=[r.model_dump() for r in res],
            )

            await s.merge(dashboard)
            await s.commit()
            logger.debug(f"更新SLB: {res}")
        except Exception as e:
            logger.error(f"更新数据库工单信息失败, 工单信息为: {res} 失败原因为: {e}")


async def update_inspect(): ...
