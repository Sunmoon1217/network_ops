"""存量资产登记（T4）：``(source_type, source_id)`` → 一条 ``ConfigurationItem``。

原资产表零改动，只登记不复制字段；``ci_id`` 保持不透明，来源用本表定位。
细节与生命周期策略见 handbook/assets.md「存量资产登记」。
"""

from django.db import models

from .ci import CIType, ConfigurationItem


class CIObjectType:
    """登记来源的类型；与 ``CIType`` 一一对应（同一类资产用同一个词，便于对照）。"""

    DEVICE = CIType.DEVICE
    IP_ADDRESS = CIType.IP_ADDRESS
    SUBNET = CIType.SUBNET


CI_OBJECT_CHOICES = (
    (CIObjectType.DEVICE, "网络设备"),
    (CIObjectType.IP_ADDRESS, "IP 地址"),
    (CIObjectType.SUBNET, "网段"),
)


class CIObjectLink(models.Model):
    """一条存量记录 ↔ 一条 CI：``(source_type, source_id)`` 唯一，``ci`` 一对一。

    ``save()`` 校验 ``ci.ci_type`` 与 ``source_type`` 一致，兜住 ORM 直写。
    """

    ci = models.OneToOneField(ConfigurationItem, on_delete=models.CASCADE, related_name="object_link", verbose_name="配置项")
    source_type = models.CharField(max_length=32, choices=CI_OBJECT_CHOICES, verbose_name="来源类型")
    source_id = models.BigIntegerField(verbose_name="来源记录 ID")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "存量资产映射"
        verbose_name_plural = verbose_name
        ordering = ("source_type", "source_id")
        constraints = (models.UniqueConstraint(fields=["source_type", "source_id"], name="uni_ci_object_source"),)
        indexes = (models.Index(fields=["source_type"], name="ci_obj_link_type_idx"),)

    def save(self, *args, **kwargs):
        if self.ci.ci_type != self.source_type:
            raise ValueError(f"CIObjectLink 要求 ci_type={self.source_type}，收到 {self.ci.ci_type}")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.source_type}#{self.source_id} → {self.ci.ci_id}"
