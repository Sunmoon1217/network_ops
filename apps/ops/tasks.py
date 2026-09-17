"""Celery 异步任务 - 采集→解析→存储阶段式工作流"""
import logging
import time

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


# ---------------------------------------------------------------------------
# 阶段式任务（采集→解析→存储）
# ---------------------------------------------------------------------------

@shared_task(bind=True, name="ops.run_collection_stage")
def run_collection_stage(self, stage_id):
    """采集阶段 - 通过连接设备获取配置"""
    logger.info("Starting collection stage %s", stage_id)
    try:
        from core.models import Stage
        stage = Stage.objects.get(id=stage_id)
        device = stage.task.device
        if not device:
            raise ValueError("任务无关联设备")

        # 获取设备连接
        connection = device.connections.filter(enabled=True).first()
        if not connection:
            raise ValueError(f"设备 {device.hostname} 无可用连接")

        # TODO: 调用实际采集器（napalm/netmiko）
        # 目前返回占位结果
        config_text = f"# placeholder config for {device.hostname}"

        _update_stage_status(stage_id, "success", output_data={"config": config_text})
    except Exception as e:
        logger.exception("Collection stage %s failed", stage_id)
        _update_stage_status(stage_id, "failed", error_message=str(e))


@shared_task(bind=True, name="ops.run_parsing_stage")
def run_parsing_stage(self, stage_id):
    """解析阶段 - 解析配置文本为结构化数据"""
    logger.info("Starting parsing stage %s", stage_id)
    try:
        from core.models import Stage
        stage = Stage.objects.get(id=stage_id)
        task = stage.task
        device = task.device

        # 从采集阶段获取原始配置
        collection_stage = task.stages.filter(stage_type="collection", status="success").first()
        if not collection_stage or not collection_stage.output_data:
            raise ValueError("无成功的采集阶段")

        raw_config = collection_stage.output_data.get("config", "")

        # 选择解析器
        from ops.parsers.factory import ParserFactory
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


@shared_task(bind=True, name="ops.run_storage_stage")
def run_storage_stage(self, stage_id):
    """存储阶段 - 将解析结果保存到数据库"""
    logger.info("Starting storage stage %s", stage_id)
    try:
        from core.models import Stage
        stage = Stage.objects.get(id=stage_id)
        task = stage.task
        device = task.device

        # 从解析阶段获取结构化数据
        parsing_stage = task.stages.filter(stage_type="parsing", status="success").first()
        if not parsing_stage or not parsing_stage.output_data:
            raise ValueError("无成功的解析阶段")

        parsed_data = parsing_stage.output_data

        # 选择 Saver
        from ops.savers.registry import get_savers_for_config
        savers = get_savers_for_config(device.device_type, parsed_data)

        total_created, total_updated = 0, 0
        for key, saver in savers:
            created, updated = saver.save(device, {key: parsed_data.get(key)})
            total_created += created
            total_updated += updated

        _update_stage_status(stage_id, "success", output_data={"created": total_created, "updated": total_updated})
    except Exception as e:
        logger.exception("Storage stage %s failed", stage_id)
        _update_stage_status(stage_id, "failed", error_message=str(e))


# ---------------------------------------------------------------------------
# DeviceConfig 异步任务
# ---------------------------------------------------------------------------

@shared_task(bind=True, name="ops.run_config_parsing")
def run_config_parsing(self, config_id):
    """异步解析 DeviceConfig"""
    from assets.models import DeviceConfig
    from ops.config_repo import get_config
    from ops.parsers.factory import ParserFactory

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
            config_json=parsed_data, parse_duration=round(duration, 3),
        )
        logger.info("Config parsing completed: %s (%.3fs)", config_id, duration)
    except Exception:
        logger.exception("Config parsing failed: %s", config_id)
        raise


@shared_task(bind=True, name="ops.run_config_storage")
def run_config_storage(self, config_id):
    """异步存储 DeviceConfig 解析结果"""
    from assets.models import DeviceConfig
    from ops.savers.registry import get_savers_for_config

    logger.info("Starting config storage for DeviceConfig %s", config_id)
    try:
        config = DeviceConfig.objects.select_related("device").get(id=config_id)
        device = config.device

        if not config.config_json:
            logger.warning("DeviceConfig %s config_json 为空，跳过", config_id)
            return

        savers = get_savers_for_config(device.device_type, config.config_json)
        total_created, total_updated = 0, 0
        for key, saver in savers:
            created, updated = saver.save(device, config.config_json)
            total_created += created
            total_updated += updated

        logger.info("Config storage completed: +%d ~%d", total_created, total_updated)
    except Exception:
        logger.exception("Config storage failed: %s", config_id)
        raise
