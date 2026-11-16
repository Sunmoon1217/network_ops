"""ingest 侧的配置任务投递：把一条 DeviceConfig 的「解析 → 存储」串成 celery 链。

通用的任务控制（建任务 / 投递阶段 / 取消）已经下沉到 ``core.tasks``；阶段之间的推进
（``collection → parsing → storage``）是 ingest 的链路知识，留在 ``ingest/signals.py``。
本模块只剩批量导入用的那条旁路链。
"""

import logging
from typing import TYPE_CHECKING, cast

from celery import chain

from ingest.tasks import run_config_parsing, run_config_storage

if TYPE_CHECKING:
    from celery import Task as CeleryTask

logger = logging.getLogger(__name__)


def submit_config_job(config_id: int) -> None:
    """把一条 DeviceConfig 的「解析 → 存储」投递成 celery 链（批量导入用）。

    两个任务都要拿到 ``config_id``，所以第二个用 ``.si()``（immutable）：默认的 ``.s()``
    会把上一个任务的返回值当参数传下去，而解析任务的返回值是 None。
    """
    # 运行时它们是 Task 实例（有 .si/.delay），stubs 只看成普通函数：cast 比 type: ignore
    # 好，因为保住了对 .si 这个名字的检查。
    parsing = cast("CeleryTask", run_config_parsing)
    storage = cast("CeleryTask", run_config_storage)

    chain(parsing.si(config_id), storage.si(config_id)).apply_async()
    logger.info("已投递配置解析链: DeviceConfig %s", config_id)
