"""Celery 异步任务 - 采集→解析→存储阶段式工作流"""

import logging
import time
from functools import lru_cache

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


def _update_stage_status(stage_id, status, output_data=None, error_message=""):
    """更新阶段状态"""
    from core.models import Stage

    stage = Stage.objects.get(id=stage_id)
    now = timezone.now()
    if status == "running":
        stage.started_at = now
    elif status in ("success", "failed"):
        stage.completed_at = now
    stage.status = status
    if output_data is not None:
        stage.output_data = output_data
    if error_message:
        stage.error_message = error_message
    stage.save()


@shared_task(bind=True, name="ingest.run_collection_stage")
def run_collection_stage(self, stage_id):
    """采集阶段 - 通过连接设备获取配置"""
    logger.info("Starting collection stage %s", stage_id)
    try:
        from core.models import Stage

        stage = Stage.objects.get(id=stage_id)
        device = stage.task.device
        if not device:
            raise ValueError("任务无关联设备")

        connection = device.connections.filter(enabled=True).first()
        if not connection:
            raise ValueError(f"设备 {device.hostname} 无可用连接")

        # TODO: 调用实际采集器（napalm/netmiko），目前是占位结果
        config_text = f"# placeholder config for {device.hostname}"

        _update_stage_status(stage_id, "success", output_data={"config": config_text})
    except Exception as e:
        logger.exception("Collection stage %s failed", stage_id)
        _update_stage_status(stage_id, "failed", error_message=str(e))
        # 必须向上抛：否则 Celery 会把失败任务记为 SUCCESS，
        # 导致 AsyncResult / Flower 的失败告警与重试全部失效
        raise


@shared_task(bind=True, name="ingest.run_parsing_stage")
def run_parsing_stage(self, stage_id):
    """解析阶段 - 解析配置文本为结构化数据"""
    logger.info("Starting parsing stage %s", stage_id)
    try:
        from core.models import Stage

        stage = Stage.objects.get(id=stage_id)
        task = stage.task
        device = task.device
        if device is None:
            raise ValueError("任务未关联设备，无法解析")

        collection_stage = task.stages.filter(stage_type="collection", status="success").first()
        if not collection_stage or not collection_stage.output_data:
            raise ValueError("无成功的采集阶段")

        raw_config = collection_stage.output_data.get("config", "")

        from ingest.parsers.factory import ParserFactory

        try:
            parser = ParserFactory.get_parser(device)
        except ValueError:
            logger.warning("设备 %s 无匹配解析器，跳过解析", device.hostname)
            _update_stage_status(stage_id, "success", output_data={"raw": raw_config})
            return

        parsed_data = parser.parse(raw_config)
        _update_stage_status(stage_id, "success", output_data=parsed_data)
    except Exception as e:
        logger.exception("Parsing stage %s failed", stage_id)
        _update_stage_status(stage_id, "failed", error_message=str(e))
        # 同采集阶段：不抛出会让 Celery 记成 SUCCESS
        raise


@shared_task(bind=True, name="ingest.run_storage_stage")
def run_storage_stage(self, stage_id):
    """存储阶段 - 将解析结果保存到数据库"""
    logger.info("Starting storage stage %s", stage_id)
    try:
        from core.models import Stage

        stage = Stage.objects.get(id=stage_id)
        task = stage.task
        device = task.device
        if device is None:
            raise ValueError("任务未关联设备，无法入库")

        parsing_stage = task.stages.filter(stage_type="parsing", status="success").first()
        if not parsing_stage or not parsing_stage.output_data:
            raise ValueError("无成功的解析阶段")

        parsed_data = parsing_stage.output_data

        # 分组规则（一个 Saver 可注册多个 key、payload 只含自己有值的键）见 build_saver_payloads
        from ingest.savers.registry import build_saver_payloads

        total_created, total_updated = 0, 0
        for saver, payload in build_saver_payloads(device.device_type, parsed_data):
            created, updated = saver.save(device, payload)
            total_created += created
            total_updated += updated

        _update_stage_status(stage_id, "success", output_data={"created": total_created, "updated": total_updated})

        # 配置行已更新 → 请求刷新软资产（信号内合并到事务提交后执行）
        from assets.signals import request_soft_asset_sync

        request_soft_asset_sync("存储阶段完成")
    except Exception as e:
        logger.exception("Storage stage %s failed", stage_id)
        _update_stage_status(stage_id, "failed", error_message=str(e))
        # 同采集/解析阶段：不抛出会让 Celery 记成 SUCCESS
        raise


@shared_task(bind=True, name="ingest.run_config_parsing")
def run_config_parsing(self, config_id):
    """异步解析 DeviceConfig"""
    from assets.models import DeviceConfig
    from ingest.config_repo import get_config
    from ingest.parsers.factory import ParserFactory

    logger.info("Starting config parsing for DeviceConfig %s", config_id)
    try:
        config = DeviceConfig.objects.select_related("device").get(id=config_id)
        device = config.device

        raw_config = get_config(device.hostname, config.git_commit_hash)
        if not raw_config:
            raise ValueError(f"Git 无配置: {config.git_commit_hash}")

        try:
            parser = ParserFactory.get_parser(device)
        except ValueError as e:
            raise ValueError(f"设备 {device.hostname} 无可用解析器: {e}")

        start = time.time()
        parsed_data = parser.parse(raw_config)
        duration = time.time() - start

        DeviceConfig.objects.filter(id=config_id).update(
            config_json=parsed_data,
            parse_duration=round(duration, 3),
        )
        logger.info("Config parsing completed: %s (%.3fs)", config_id, duration)
    except Exception:
        logger.exception("Config parsing failed: %s", config_id)
        raise


@shared_task(bind=True, name="ingest.run_config_storage")
def run_config_storage(self, config_id):
    """异步存储 DeviceConfig 解析结果"""
    from assets.models import DeviceConfig

    logger.info("Starting config storage for DeviceConfig %s", config_id)
    try:
        config = DeviceConfig.objects.select_related("device").get(id=config_id)
        device = config.device

        if not config.config_json:
            logger.warning("DeviceConfig %s config_json 为空，跳过", config_id)
            return

        # 与 run_storage_stage 同一套分组：每个 Saver 只拿到自己注册的 key
        from ingest.savers.registry import build_saver_payloads

        total_created, total_updated = 0, 0
        for saver, payload in build_saver_payloads(device.device_type, config.config_json):
            created, updated = saver.save(device, payload)
            total_created += created
            total_updated += updated

        logger.info("Config storage completed: +%d ~%d", total_created, total_updated)

        # 批量导入链：storage 是最后一环，之后刷新软资产
        from assets.signals import request_soft_asset_sync

        request_soft_asset_sync(f"批量导入存储完成: DeviceConfig {config_id}")
    except Exception:
        logger.exception("Config storage failed: %s", config_id)
        raise


# ---------------------------------------------------------------------------
# Dashboard 采集任务：采集与存储分离（采集编排见 ingest/collectors/dashboard.py）
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _dashboard_redis():
    """C 方案下中转 payload 的连接池；A 方案不会调用到。"""
    import redis
    from django.conf import settings

    return redis.from_url(settings.REDIS_URL, socket_timeout=10, socket_connect_timeout=5)


def _deliver(payload):
    """A：payload 随消息直接投递；C：payload 写 Redis，只把 key 交给写库任务。"""
    import json
    from uuid import uuid4

    from django.conf import settings

    if not settings.DASHBOARD_PAYLOAD_VIA_REDIS:
        return payload
    key = f"dashboard:batch:{uuid4().hex}"
    _dashboard_redis().set(key, json.dumps(payload), ex=settings.DASHBOARD_PAYLOAD_TTL)
    return {"__redis_key__": key}


@shared_task(name="ingest.collect_dashboard")
def collect_dashboard(source):
    """采集一个数据源 → 按任务名投递给 analysis 的写库任务；**本任务不写数据库**。

    ingest 侧只认 ``settings.DASHBOARD_WRITE_TASK`` 这个字符串（与 access_flow_trigger
    同一套接缝），绝不 import analysis；async 采集与同步投递分开，ORM 不会进 event loop。
    采集失败仍投递一条 failed 记录让大屏可见数据新鲜度，随后向上抛让 Celery 记 FAILURE。
    """
    import asyncio

    from celery import current_app
    from django.conf import settings
    from django.utils import timezone

    from ingest.collectors.dashboard import DashboardPayload, collect

    failed: Exception | None = None
    payload: DashboardPayload
    try:
        payload = asyncio.run(collect(source))
    except Exception as exc:
        logger.exception("Dashboard 采集任务异常: source=%s", source)
        failed = exc
        now = timezone.now().isoformat()
        payload = {
            "source": source,
            "batch_at": now,
            "metrics": [],
            "samples": [],
            "cases": [],
            "run": {"status": "failed", "item_count": 0, "started_at": now, "finished_at": now, "error": str(exc)},
        }

    current_app.send_task(settings.DASHBOARD_WRITE_TASK, args=[_deliver(payload)])
    if failed is not None:
        raise failed

    logger.info(
        "Dashboard 采集已投递: source=%s, metrics=%d, samples=%d, run=%s",
        source,
        len(payload["metrics"]),
        len(payload["samples"]),
        payload["run"]["status"],
    )
    return {
        "source": source,
        "run": payload["run"],
        "metrics": len(payload["metrics"]),
        "samples": len(payload["samples"]),
        "cases": len(payload["cases"]),
    }


@shared_task(name="ingest.refresh_link_cache")
def refresh_link_cache_task():
    """大屏链路带宽：Zabbix 直取 → Redis（不落库）。

    失败分两类，刻意区别对待：

    - **全部链路采集失败**（``LinkCollectionError``，外部数据源整体不可用）属可预期故障：
      只记一条 ``logger.error``（消息里是各 target 的原因摘要，单行），任务返回
      ``{"status": "failed", ...}``，**不 raise**——Celery 不会打整段 traceback，下个周期
      自动重试。这是为了压掉 180s 一轮的刷屏日志。
    - **其它异常**（Redis 不可用、``conf/links.json`` 非法等真实故障）照常向上抛，
      让 Celery 记 FAILURE 并保留 traceback。

    单条链路失败只在 ``link_cache`` 里 warning，本任务照常返回摘要。
    """
    from ingest.collectors.link_cache import LinkCollectionError, refresh_link_cache

    try:
        summary = refresh_link_cache()
    except LinkCollectionError as exc:
        logger.error("链路缓存刷新失败（全部链路不可用，下个周期重试）: %s", exc)
        return {"status": "failed", "error": str(exc)}

    logger.info("链路缓存刷新完成: %s", summary)
    return {"status": "success", **summary}
