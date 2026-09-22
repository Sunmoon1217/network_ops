"""Celery 异步任务 - 采集→解析→存储阶段式工作流"""

import logging
import time

from celery import shared_task
from django.conf import settings
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

        # 从采集阶段获取原始配置
        collection_stage = task.stages.filter(stage_type="collection", status="success").first()
        if not collection_stage or not collection_stage.output_data:
            raise ValueError("无成功的采集阶段")

        raw_config = collection_stage.output_data.get("config", "")

        # 选择解析器
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

        # 从解析阶段获取结构化数据
        parsing_stage = task.stages.filter(stage_type="parsing", status="success").first()
        if not parsing_stage or not parsing_stage.output_data:
            raise ValueError("无成功的解析阶段")

        parsed_data = parsing_stage.output_data

        # 选择 Saver。get_savers_for_config 的第一个元素是**key 列表**（一个 Saver
        # 可能注册多个 key，如 PolicySaver 的 policies/acl/rules），必须整组交给它，
        # 不能当成单个 key——原先 {key: parsed_data.get(key)} 会抛
        # TypeError: unhashable type: 'list'
        from ingest.savers.registry import build_saver_payloads

        total_created, total_updated = 0, 0
        for saver, payload in build_saver_payloads(device.device_type, parsed_data):
            created, updated = saver.save(device, payload)
            total_created += created
            total_updated += updated

        _update_stage_status(stage_id, "success", output_data={"created": total_created, "updated": total_updated})
    except Exception as e:
        logger.exception("Storage stage %s failed", stage_id)
        _update_stage_status(stage_id, "failed", error_message=str(e))
        # 同采集/解析阶段：不抛出会让 Celery 记成 SUCCESS
        raise


# ---------------------------------------------------------------------------
# DeviceConfig 异步任务
# ---------------------------------------------------------------------------


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

        # 与 run_storage_stage 用同一套分组规则：每个 Saver 只拿到自己注册的 key。
        # 原先直接把整个 config_json 递进去，等于让 Saver 能看到不属于它的键，
        # 注册的 key 写错了也测不出来。
        from ingest.savers.registry import build_saver_payloads

        total_created, total_updated = 0, 0
        for saver, payload in build_saver_payloads(device.device_type, config.config_json):
            created, updated = saver.save(device, payload)
            total_created += created
            total_updated += updated

        logger.info("Config storage completed: +%d ~%d", total_created, total_updated)
    except Exception:
        logger.exception("Config storage failed: %s", config_id)
        raise


# ---------------------------------------------------------------------------
# 访问流（AccessFlow）重建：生产者侧
# ---------------------------------------------------------------------------


@shared_task(
    bind=True,
    name="ingest.rebuild_access_flows",
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

    写库只有 ``access_flow_consumer`` 一个进程（单写者，见 ``ingest/access_stream.py``）。
    路由到独立的 ``access_flow`` 队列（settings 的 CELERY_TASK_ROUTES），与采集/解析/
    存储三阶段任务隔离。
    """
    from ingest.access_stream import backlog, device_lock, publish
    from ingest.policy_expand import collect_device_flows

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
