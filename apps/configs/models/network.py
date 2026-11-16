"""网络配置行模型。

拆分第 1 步只迁了 ``Vlan``（最小验证切片）：先证明「新 app + RENAME 迁移 + 存量库/fresh 库
双路径」这条路走得通，再批量迁其余子类。**其余 23 个 ConfigBase 子类仍在
``assets/models/network.py``**，它们暂时反向 import 本模块的基类——这个方向是过渡态，
迁完即消失（见 ``handbook/design/assets-configs-split.md`` §建议的最小验证切片）。
"""

from django.db import models

from .base import ConfigBase


class Vlan(ConfigBase):
    """VLAN"""

    vid = models.PositiveIntegerField(verbose_name="VLAN ID")
    name = models.CharField(max_length=100, blank=True, default="", verbose_name="VLAN名称")
    description = models.CharField(max_length=255, blank=True, default="", verbose_name="描述")

    class Meta:
        verbose_name = "VLAN"
        verbose_name_plural = verbose_name
        ordering = ("vid",)
        constraints = (models.UniqueConstraint(fields=["device", "vid"], name="uni_vlan_device_vid"),)

    def __str__(self):
        return f"{self.device.hostname} - VLAN {self.vid}" + (f" ({self.name})" if self.name else "")
