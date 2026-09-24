"""分析域的 Celery 任务：访问流（AccessFlow）重建——生产者侧。

2026-09 由 ingest.tasks 迁入：任务名 ``ingest.rebuild_access_flows`` →
``analysis.rebuild_access_flows``（settings 的 ``CELERY_TASK_ROUTES`` 同步改）。
ingest 侧的投递触点 ``ingest.access_flow_trigger`` 按 ``settings.ACCESS_FLOW_TASK``
字符串 send_task，不 import 本模块——依赖方向 analysis → ingest 单向。
"""

import logging

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="analysis.rebuild_access_flows",
    # 只在本任务上开「执行完才 ack」：worker 崩溃 / 被杀时任务重回队列自动重投。
    # 展开是幂等投递（消费侧 handle_message 幂等），重投不脏数据。
    acks_late=True,
    reject_on_worker_lost=True,
    # 背压与锁竞争都走 countdown=2 的 retry，150 次 ≈ 5 分钟上限——队列持续堵塞时
    # 必须以可见的 FAILURE 收场，而不是无限重试把问题埋掉。
    max_retries=150,
    default_retry_delay=10,
)
def rebuild_access_flows(self, device_id):
    """生产者：展开一台设备的策略，结果投进 Redis Stream——**不写库**。

    写库只有 ``access_flow_consumer`` 一个进程（单写者，见 ``analysis/access_stream.py``）。
    路由到独立的 ``access_flow`` 队列（settings 的 CELERY_TASK_ROUTES），与采集/解析/
    存储三阶段任务隔离。
    """
    from analysis.access_stream import backlog, device_lock, publish
    from analysis.policy_expand import collect_device_flows

    # 1) 背压：下游积压就退出重试。绝不在任务里 sleep 等待——那会占死这个 worker
    #    进程，执行队列的进程全被占住就整池瘫痪；self.retry 立即结束任务、释放进程。
    try:
        waiting = backlog() > settings.ACCESS_FLOW_MAX_QUEUE
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2)

    # 2) 同设备互斥：拿不到锁说明另一份任务（可能是重投的）正在跑，同样退出重试
    if waiting:
        raise self.retry(countdown=2)

    from assets.models import Device

    with device_lock(device_id) as acquired:
        if not acquired:
            raise self.retry(countdown=2)

        device = Device.objects.filter(pk=device_id).first()
        if device is None:
            return 0  # 设备已删，无事可做

        try:
            flows = collect_device_flows(device)
            publish(device, flows)
        except Exception as exc:
            # redis 不可达等瞬时故障：转成重试，acks_late 兜底（进程死了也能重投）
            raise self.retry(exc=exc, countdown=2)

    logger.info("设备 %s 访问流展开已投递: %s 个组合", device.hostname, len(flows))
    return len(flows)
