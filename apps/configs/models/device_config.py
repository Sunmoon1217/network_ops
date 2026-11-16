"""设备配置快照：某设备在某 commit 上的 config_json。

从 ``assets/models/network.py`` 迁入（拆分切片 2）。刻意**不继承** ConfigBase：
CI 台账不能被 ``purge_configs`` 的 ``ConfigBase.__subclasses__()`` 枚举清理。
device 用字符串引用 assets.Device，与 configs/models/base.py 同样避免 app registry 未就绪时
import 业务模型。
"""

from typing import TYPE_CHECKING

from django.db import models


class DeviceConfig(models.Model):
    device = models.ForeignKey("assets.Device", on_delete=models.CASCADE, related_name="configs", verbose_name="关联设备")
    git_commit_hash = models.CharField(max_length=40, verbose_name="Git Commit Hash")
    config_json = models.JSONField(blank=True, null=True, verbose_name="解析后的配置数据")
    parse_duration = models.FloatField(null=True, blank=True, verbose_name="解析耗时(秒)")
    collected_at = models.DateTimeField(auto_now_add=True, verbose_name="采集时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "设备配置"
        verbose_name_plural = verbose_name
        ordering = ("-collected_at",)

    def __str__(self):
        return f"{self.device.hostname} - {self.collected_at}"

    if TYPE_CHECKING:
        device_id: int
