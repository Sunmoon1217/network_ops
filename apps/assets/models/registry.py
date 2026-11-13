"""存量资产登记（T4）：把既有资产表映射进统一 CI 主表。

`Device` / `IPAddress` / `Subnet` 在 T1 之前就存在、字段与业务逻辑都成熟。T4 **不复制**
它们的字段、也不给原表加列，而是登记：一条 `ConfigurationItem` + 一条来源映射（本表）。

为什么需要映射表而不是给 CI 编确定性 ID（如 `DEV-123`）：`ci_id` 是**不透明**的稳定锚点
（T15 把 `CI-<12位hex>` 写进 Zabbix 主机标签），类型与主键都不该编进去；来源记录用
`(source_type, source_id)` 定位，主键换了也不影响锚点。

只登记、不做生命周期：源记录改名靠重跑 `manage.py register_assets` 同步（幂等）；源记录
删除后 CI 残留——与软资产「配置消失不删资产」同一策略，避免误删人工标注过的台账。
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

    不继承 ``ConfigBase``：这是登记台账，``purge_configs`` 清理配置解析产物时不能碰它。
    ``save()`` 校验 ``ci.ci_type`` 与 ``source_type`` 一致，兜住 ORM 直写（与 ``_CIExtension``
    同一道防线）；登记服务本身也按类型分派，正常不会触发。
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
