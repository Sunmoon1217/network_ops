"""分析域的 Celery 任务：访问流（AccessFlow）重建——生产者侧。

2026-09 由 ingest.tasks 迁入：任务名 ``ingest.rebuild_access_flows`` →
``analysis.rebuild_access_flows``（settings 的 ``CELERY_TASK_ROUTES`` 同步改）。
ingest 侧的投递触点 ``ingest.access_flow_trigger`` 按 ``settings.ACCESS_FLOW_TASK``
字符串 send_task，不 import 本模块——依赖方向 analysis → ingest 单向。
"""

import logging
from functools import lru_cache

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


# ---------------------------------------------------------------------------
# Dashboard 写库任务：接收 ingest 采集任务的 payload，是供数表唯一写入口
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _dashboard_redis():
    """C 方案下读取暂存的 payload；A 方案不会调用到。"""
    import redis

    return redis.from_url(settings.REDIS_URL, socket_timeout=10, socket_connect_timeout=5)


def _resolve_payload(delivery):
    """A：delivery 就是 payload；C：delivery 只带 Redis key（取完即删，TTL 兜底）。"""
    if isinstance(delivery, dict) and "__redis_key__" in delivery:
        import json

        key = delivery["__redis_key__"]
        raw = _dashboard_redis().get(key)
        if raw is None:
            raise ValueError(f"Dashboard payload 已过期或丢失: {key}")
        _dashboard_redis().delete(key)
        return json.loads(raw)
    return delivery


@shared_task(name=settings.DASHBOARD_WRITE_TASK)
def write_dashboard(delivery):
    """消费采集 payload → upsert 大屏表；整批一个事务，重复投递由唯一键保证幂等。"""
    from django.db import transaction
    from django.utils.dateparse import parse_datetime

    from analysis.models import CollectionRun, DashboardMetric, ItsmCase, MetricSample

    payload = _resolve_payload(delivery)
    with transaction.atomic():
        for row in payload["metrics"]:
            DashboardMetric.objects.update_or_create(
                panel=row["panel"],
                group=row["group"],
                name=row["name"],
                defaults={
                    "value": row.get("value"),
                    "list_value": row.get("list_value") or [],
                    "sampled_at": parse_datetime(row["sampled_at"]) if row.get("sampled_at") else None,
                },
            )

        for row in payload["samples"]:
            MetricSample.objects.update_or_create(
                kind=row["kind"],
                scope=row["scope"],
                subject=row["subject"],
                metric_key=row.get("metric_key") or "",
                sampled_at=parse_datetime(row["sampled_at"]),
                defaults={"value": row.get("value"), "payload": row.get("payload") or {}},
            )

        cases = payload["cases"]
        if cases:
            case_nos = [row["case_no"] for row in cases]
            for row in cases:
                ItsmCase.objects.update_or_create(
                    case_no=row["case_no"],
                    defaults={
                        "title": row["title"],
                        "applicant": row.get("applicant") or "",
                        "raw": row.get("raw") or {},
                        "is_active": True,
                    },
                )
                # 读模型物化成「一条工单一行」，前端 ChartsCard-2 直接按 name 取工单号
                DashboardMetric.objects.update_or_create(
                    panel="itsmtask",
                    group="case",
                    name=row["case_no"],
                    defaults={"value": None, "list_value": [row.get("raw") or {}], "sampled_at": parse_datetime(payload["batch_at"])},
                )
            # 全量快照：消失的工单保留历史但不再出现在大屏
            ItsmCase.objects.exclude(case_no__in=case_nos).update(is_active=False)
            DashboardMetric.objects.filter(panel="itsmtask", group="case").exclude(name__in=case_nos).delete()

        run = payload["run"]
        CollectionRun.objects.create(
            source=payload["source"],
            status=run["status"],
            item_count=run["item_count"],
            error=run.get("error") or "",
            started_at=parse_datetime(run["started_at"]),
            finished_at=parse_datetime(run["finished_at"]),
        )

    logger.info("Dashboard 写库完成: source=%s, status=%s, items=%s", payload["source"], run["status"], run["item_count"])
    return run["item_count"]
