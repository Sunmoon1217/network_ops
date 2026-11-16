"""配置行基类。

从 ``assets/models/network.py`` 迁入（拆分第 1 步）。``ConfigBase`` 的子类都是
「某台设备上的一条配置行」，与 assets 的设备台账是两回事——判据见 ``handbook/assets.md``
「资产分类边界」，方案见 ``handbook/design/assets-configs-split.md``。

``device`` 用**字符串**引用 ``assets.Device``（不 import assets 的模型）：configs → assets
是合法的向下依赖，但两个 models 包互相 import 会绕成环，且 app registry 尚未就绪时
import 业务模型会炸。
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
