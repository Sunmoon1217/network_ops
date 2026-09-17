"""DeviceConfig post_save 信号处理。

流程与 ``reparse`` 管理命令共用 ``ops.pipeline.run_config_pipeline``：
DeviceConfig 保存后，从 Git 读取配置原文 → 解析器解析 → 结果写回 config_json
→ 按顶层 key 分发到对应的 Saver 入库。
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

# 解析完成后写回 config_json 会再次触发 post_save，靠这里防重入
_processing = set()


@receiver(post_save, sender="assets.DeviceConfig")
def on_device_config_saved(sender, instance, created, **kwargs):
    if not created or instance.pk in _processing:
        return

    _processing.add(instance.pk)
    try:
        from ops.pipeline import run_config_pipeline

        run_config_pipeline(instance.device, instance)
    except Exception as e:
        logger.error("DeviceConfig %s 处理失败: %s", instance.pk, e, exc_info=True)
    finally:
        _processing.discard(instance.pk)
