"""工具组件"""
import logging

from django.db import transaction

logger = logging.getLogger(__name__)


def save_deviceconfig(device_obj, config_text: str) -> None:
    """保存设备配置到数据库"""
    from assets.models import DeviceConfig
    from ops.config_repo import save_config
    from ops.parsers.factory import ParserFactory
    from ops.savers.registry import get_savers_for_config

    with transaction.atomic():
        commit_hash = save_config(device_obj.hostname, config_text,
                                  message=f"update: {device_obj.hostname} config")
        config_obj = DeviceConfig(device=device_obj, git_commit_hash=commit_hash)
        config_obj.save()
        logger.info("配置元数据已保存: %s -> %s", device_obj.hostname, commit_hash[:8])

        try:
            parser = ParserFactory.get_parser(device_obj)
            parsed_data = parser.parse(config_text)
            config_obj.config_json = parsed_data
            config_obj.save(update_fields=["config_json"])
            for key, saver in get_savers_for_config(device_obj.device_type, parsed_data):
                saver.save(device_obj, {key: parsed_data.get(key)})
            logger.info("解析配置成功: %s", device_obj.hostname)
        except Exception as e:
            logger.error("配置解析失败: %s - %s", device_obj.hostname, e)
            raise
