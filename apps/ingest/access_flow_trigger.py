"""访问流（AccessFlow）重建任务的**投递触点**——ingest 侧唯一与 analysis 解耦的接缝。

链路的触发方是 ``PolicySaver``（策略落库后要重建该设备的访问流），但任务本体
``analysis.rebuild_access_flows`` 住在 analysis——依赖方向是 **analysis → ingest 单向，
ingest 不许 import analysis**。所以这里不 import 任务对象，而是按
``settings.ACCESS_FLOW_TASK`` 的**任务名字符串** send_task：

- celery 的消息本来就只有 ``{"task": <名字>, "args": [...]}``，worker 收到后拿名字查
  自己的注册表（autodiscover 已加载 analysis.tasks）执行，与投递方是否 import 过
  任务无关；
- 任务名的唯一定义处是 ``settings.ACCESS_FLOW_TASK``，任务装饰器的 ``name=`` 与
  ``CELERY_TASK_ROUTES`` 的 key 必须与之一致（tests/analysis/test_access_flow_task.py
  有对账断言，改名不同步直接红）。

开关与降级语义（与拆分前的 access_stream.request_rebuild 一致）：

- ``ACCESS_FLOW_DISPATCH`` 供测试默认关闭（conftest 统一置 False）——否则
  PolicySaver 每保存一次就把消息发进真实 Redis；
- broker 不可达**只告警不抛出**：解析入库已经成功，重建晚一点没关系
  （``manage.py rebuild_access_flows --device <H>`` 可以手工补）。
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
        logger.warning(
            "投递 AccessFlow 重建失败（可用 rebuild_access_flows 手工补）: device=%s", device_id, exc_info=True
        )
