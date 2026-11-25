"""配置行基类 ``ConfigBase``：子类都是「某台设备上的一条配置行」。

``device`` 用字符串引用 ``assets.Device``：两边的 models 包互相 import 会成环，
且 app registry 未就绪时 import 业务模型会炸。
"""

from typing import TYPE_CHECKING

from django.db import models


class ConfigBase(models.Model):
    """配置模型基类"""

    device = models.ForeignKey("assets.Device", on_delete=models.CASCADE, verbose_name="关联设备")
    is_active = models.BooleanField(default=True, verbose_name="是否生效")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    if TYPE_CHECKING:
        device_id: int

    class Meta:
        abstract = True
