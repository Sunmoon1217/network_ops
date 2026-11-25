"""分析域的 Celery 任务：访问流（AccessFlow）重建——只展开、不写库。

任务名的唯一定义处是 ``settings.ACCESS_FLOW_TASK``；ingest 侧的投递触点按字符串
send_task，不 import 本模块（依赖方向 analysis → ingest 单向）。
参数取舍与背压理由见 handbook/analysis.md
"""

import logging
from functools import lru_cache

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="analysis.rebuild_access_flows",
    # 执行完才 ack：worker 崩溃/被杀时任务重回队列自动重投（展开是幂等投递）。
    acks_late=True,
    reject_on_worker_lost=True,
    # 背压与锁竞争都走 countdown=2 的 retry，150 次 ≈ 5 分钟上限：持续堵塞必须以可见的
    # FAILURE 收场，而不是无限重试把问题埋掉。
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

    # 1) 背压：下游积压就退出重试。绝不在任务里 sleep——那会占死 worker 进程。
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
            logger.info("设备 %s 已删除，跳过访问流重建", device_id)
            return 0  # 设备已删，无事可做

        try:
            flows = collect_device_flows(device)
            publish(device, flows)
        except Exception as exc:
            # redis 不可达等瞬时故障：转成重试，acks_late 兜底（进程死了也能重投）
            raise self.retry(exc=exc, countdown=2)

    logger.info("设备 %s 访问流展开已投递: %s 个组合", device.hostname, len(flows))
    return len(flows)


# Dashboard 写库任务：接收 ingest 采集任务的 payload，是供数表唯一写入口


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
    from django.utils import timezone
    from django.utils.dateparse import parse_datetime

    from analysis.models import CollectionRun, DashboardMetric, ItsmCase, MetricSample

    payload = _resolve_payload(delivery)
    try:
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
                    # 读模型物化成「一条工单一行」，前端 AutomationTicketWidget 直接按 name 取工单号
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
    except Exception as e:
        # 写库失败不能只在 celery 里红一下：CollectionRun 是大屏数据新鲜度的来源，
        # 补一条 failed 记录（主事务已回滚，这里另起事务），随后照常上抛让 Celery 记 FAILURE。
        logger.exception("Dashboard 写库失败: source=%s", payload.get("source"))
        failed_run = payload.get("run") or {}
        source = payload.get("source")
        if source:
            try:
                CollectionRun.objects.create(
                    source=source,
                    status="failed",
                    item_count=0,
                    error=str(e)[:2000],
                    started_at=parse_datetime(failed_run.get("started_at") or "") or timezone.now(),
                    finished_at=timezone.now(),
                )
            except Exception:
                logger.exception("Dashboard 失败记录写入失败")
        raise

    logger.info("Dashboard 写库完成: source=%s, status=%s, items=%s", payload["source"], run["status"], run["item_count"])
    return run["item_count"]


# 巡检：调度（读目标投采集）/ 写库（唯一入口）/ 滚存清理。口径见 handbook/analysis.md「巡检」


@shared_task(name=settings.INSPECTION_DISPATCH_TASK)
def dispatch_inspection(date_start=None, date_end=None):
    """读启用的接口带宽目标 → 投递 ingest 巡检采集任务（本任务不碰 Zabbix）。

    日期为空时由采集器取「昨天」，手动补数可传 ``date_start`` / ``date_end``。
    """
    from celery import current_app

    from analysis.models import InspectionTarget

    targets = list(InspectionTarget.objects.filter(enabled=True).values("host", "ifname", "itemids"))
    current_app.send_task(settings.INSPECTION_COLLECT_TASK, args=[date_start, date_end, targets])
    logger.info("巡检采集已投递: %s ~ %s, targets=%d", date_start, date_end, len(targets))
    return {"date_start": date_start, "date_end": date_end, "targets": len(targets)}


@shared_task(name=settings.INSPECTION_WRITE_TASK)
def write_inspection(payload):
    """巡检唯一写库入口：upsert 日指标与批次，并把当天设备行物化成大屏巡检面板。

    物化只在当天有设备数据时进行——一次采集失败不清空上次成功的结果。
    """
    from django.db import transaction
    from django.utils import timezone
    from django.utils.dateparse import parse_date, parse_datetime

    from analysis.models import DashboardMetric, DeviceMetricDaily, InspectionRun, InterfaceMetricDaily

    devices = payload.get("devices") or []
    interfaces = payload.get("interfaces") or []
    run = payload.get("run") or {}
    batch_date = parse_date(payload.get("date_end") or "") or timezone.localdate()

    try:
        with transaction.atomic():
            for row in devices:
                DeviceMetricDaily.objects.update_or_create(
                    date=parse_date(row["date"]),
                    host=row["host"],
                    defaults={
                        "cpu_avg": row.get("cpu_avg"),
                        "cpu_max": row.get("cpu_max"),
                        "memory_avg": row.get("memory_avg"),
                        "memory_max": row.get("memory_max"),
                        "payload": row.get("payload") or {},
                    },
                )

            for row in interfaces:
                InterfaceMetricDaily.objects.update_or_create(
                    date=parse_date(row["date"]),
                    host=row["host"],
                    ifname=row["ifname"],
                    defaults={
                        "in_bps_avg": row.get("in_bps_avg"),
                        "in_bps_max": row.get("in_bps_max"),
                        "out_bps_avg": row.get("out_bps_avg"),
                        "out_bps_max": row.get("out_bps_max"),
                        "in_usage_avg": row.get("in_usage_avg"),
                        "in_usage_max": row.get("in_usage_max"),
                        "out_usage_avg": row.get("out_usage_avg"),
                        "out_usage_max": row.get("out_usage_max"),
                        "payload": row.get("payload") or {},
                    },
                )

            InspectionRun.objects.update_or_create(
                date=batch_date,
                defaults={
                    "status": run.get("status") or "success",
                    "device_count": len(devices),
                    "interface_count": len(interfaces),
                    "error": run.get("error") or "",
                    "started_at": parse_datetime(run.get("started_at") or "") or timezone.now(),
                    "finished_at": parse_datetime(run.get("finished_at") or "") or timezone.now(),
                },
            )

            day_rows = [row for row in devices if row.get("date") == payload.get("date_end")]
            if day_rows:
                DashboardMetric.objects.update_or_create(
                    panel="inspection",
                    group="device",
                    name="list",
                    defaults={
                        "value": None,
                        "list_value": [
                            {
                                "name": row["host"],
                                "cpu_avg": row.get("cpu_avg"),
                                "cpu_max": row.get("cpu_max"),
                                "memory_avg": row.get("memory_avg"),
                                "memory_max": row.get("memory_max"),
                            }
                            for row in day_rows
                        ],
                        "sampled_at": timezone.now(),
                    },
                )
    except Exception as exc:
        logger.exception("巡检写库失败: date_end=%s", payload.get("date_end"))
        try:
            InspectionRun.objects.update_or_create(
                date=batch_date,
                defaults={
                    "status": "failed",
                    "device_count": 0,
                    "interface_count": 0,
                    "error": str(exc)[:2000],
                    "started_at": parse_datetime(run.get("started_at") or "") or timezone.now(),
                    "finished_at": timezone.now(),
                },
            )
        except Exception:
            logger.exception("巡检失败批次写入失败")
        raise

    logger.info("巡检写库完成: date_end=%s, devices=%d, interfaces=%d", payload.get("date_end"), len(devices), len(interfaces))
    return {"devices": len(devices), "interfaces": len(interfaces)}


@shared_task(name=settings.INSPECTION_PRUNE_TASK)
def prune_inspection():
    """滚存：删除业务日期早于保留期的日指标与批次；``INSPECTION_RETENTION_DAYS <= 0`` 跳过。"""
    from datetime import timedelta

    from django.db import transaction
    from django.utils import timezone

    from analysis.models import DeviceMetricDaily, InspectionRun, InterfaceMetricDaily

    days = settings.INSPECTION_RETENTION_DAYS
    if days <= 0:
        logger.info("巡检保留期为 0（永久保留），跳过清理")
        return {"skipped": True}

    cutoff = timezone.localdate() - timedelta(days=days)
    with transaction.atomic():
        device_deleted = DeviceMetricDaily.objects.filter(date__lt=cutoff).delete()[0]
        interface_deleted = InterfaceMetricDaily.objects.filter(date__lt=cutoff).delete()[0]
        run_deleted = InspectionRun.objects.filter(date__lt=cutoff).delete()[0]

    summary = {"cutoff": cutoff.isoformat(), "devices": device_deleted, "interfaces": interface_deleted, "runs": run_deleted}
    logger.info("巡检滚存完成: %s", summary)
    return summary
