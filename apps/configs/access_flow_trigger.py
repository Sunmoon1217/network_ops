"""访问流重建任务的投递触点：PolicySaver（configs）→ analysis 任务。

configs 不许 import analysis，所以按 ``settings.ACCESS_FLOW_TASK`` 的任务名 ``send_task``。
任务名与路由 key 必须一致（测试对账）；开关与降级语义见 handbook/analysis.md。
"""

from logging import getLogger

from celery import current_app
from django.conf import settings

logger = getLogger(__name__)


def request_rebuild(device_id: int) -> None:
    """投递「重建一台设备的访问流」任务（按任务名字符串 send_task，不 import analysis）。"""
    if not settings.ACCESS_FLOW_DISPATCH:
        return
    try:
        current_app.send_task(settings.ACCESS_FLOW_TASK, args=[device_id])
    except Exception:
        logger.warning("投递 AccessFlow 重建失败（可用 rebuild_access_flows 手工补）: device=%s", device_id, exc_info=True)
