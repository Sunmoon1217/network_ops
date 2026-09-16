"""DeviceConfig post_save 信号处理

流程:
1. DeviceConfig 保存后触发
2. 从 Git 读取配置原文 → 解析器解析 → 结果写回 config_json
3. 如果 config_json 已有数据，从不同 key 分发到对应的 Saver 保存到数据库
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

_processing = set()


@receiver(post_save, sender="assets.DeviceConfig")
def on_device_config_saved(sender, instance, created, **kwargs):
    if not created or instance.pk in _processing:
        return

    _processing.add(instance.pk)
    try:
        device = instance.device
        # 堆叠组备机不持有配置：若备机意外产生了 DeviceConfig，解析归属主设备，这里直接跳过
        from ops.config_owner import resolve_config_owner

        owner = resolve_config_owner(device)
        if owner.pk != device.pk:
            logger.warning("设备 %s 是堆叠备机，配置归属 %s，跳过解析", device.hostname, owner.hostname)
            return

        hostname = device.hostname
        commit_hash = instance.git_commit_hash

        # 1. 如果 config_json 为空或不是字典，从 Git 读取并解析
        config_json = instance.config_json if isinstance(instance.config_json, dict) else {}
        if not config_json:
            from ops.config_repo import get_config

            raw_text = get_config(hostname, commit_hash)
            if not raw_text:
                logger.warning(
                    "DeviceConfig %s: Git 无配置 (hash=%s)", instance.pk, commit_hash[:8] if commit_hash else "None"
                )
                return

            from ops.parsers.factory import ParserFactory

            try:
                parser = ParserFactory.get_parser(device)
            except ValueError as e:
                logger.warning("设备 %s 无匹配解析器: %s", hostname, e)
                return

            config_json = parser.parse(raw_text)
            instance.config_json = config_json
            instance.save(update_fields=["config_json", "updated_at"])
            logger.info("设备 %s 配置解析完成", hostname)

        # 2. config_json 有数据 → 分发到 Saver
        if config_json:
            from ops.savers.registry import get_savers_for_config

            savers = get_savers_for_config(device.device_type, config_json)
            for keys, saver in savers:
                label = ",".join(keys)
                try:
                    # 命中同一 Saver 的多个键要一起传，否则 Saver 内的兜底链只看到第一个
                    payload = {key: config_json[key] for key in keys if config_json.get(key)}
                    if payload:
                        created_n, updated_n = saver.save(device, payload)
                        logger.info("设备 %s [%s] 保存完成: +%d ~%d", hostname, label, created_n, updated_n)
                except Exception as e:
                    logger.error("设备 %s [%s] 保存失败: %s", hostname, label, e, exc_info=True)

    except Exception as e:
        logger.error("DeviceConfig %s 处理失败: %s", instance.pk, e, exc_info=True)
    finally:
        _processing.discard(instance.pk)
