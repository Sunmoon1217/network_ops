"""批量导入用的配置投递：把一条 ``DeviceConfig`` 的「解析 → 存储」串成 celery 链。

通用任务控制在 ``core.tasks``，阶段推进在 ``ingest/signals.py``，见 ``handbook/ingest.md``。
"""

import logging
from typing import TYPE_CHECKING, cast

from celery import chain

from ingest.tasks import run_config_parsing, run_config_storage

if TYPE_CHECKING:
    from celery import Task as CeleryTask

logger = logging.getLogger(__name__)


def submit_config_job(config_id: int) -> None:
    """把一条 ``DeviceConfig`` 的「解析 → 存储」投递成 celery 链（批量导入用）。"""
    # 运行时它们是 Task 实例（有 .si/.delay），stubs 只看成普通函数：cast 保住 .si 的名字检查
    parsing = cast("CeleryTask", run_config_parsing)
    storage = cast("CeleryTask", run_config_storage)

    # 第二个任务用 .si()（immutable）：.s() 会把上一个任务的返回值（None）当参数传下去
    chain(parsing.si(config_id), storage.si(config_id)).apply_async()
    logger.info("已投递配置解析链: DeviceConfig %s", config_id)
