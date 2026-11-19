"""批量导入用的配置投递：每份配置建一条「导入配置」任务（单阶段：解析 → 入库）。

任务机制见 ``core.tasks``，阶段推进在 ``ingest/signals.py``，链路说明见 ``handbook/ingest.md``。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.tasks import create_task

if TYPE_CHECKING:
    from core.models import Task

logger = logging.getLogger(__name__)


def submit_config_job(config_id: int) -> Task:
    """给一条 ``DeviceConfig`` 建「导入配置」任务并投递解析入库阶段。

    目标设备写成软引用（``target_*``），任务列表因此能按设备过滤、显示设备名。
    """
    from configs.models import DeviceConfig

    config = DeviceConfig.objects.select_related("device").get(pk=config_id)
    device = config.device

    task = create_task(
        "import_config",
        params={"config_id": config_id},
        target_type="device",
        target_id=device.pk,
        target_label=device.hostname,
    )
    logger.info("已投递配置解析入库任务: task=%s DeviceConfig=%s", task.pk, config_id)
    return task
