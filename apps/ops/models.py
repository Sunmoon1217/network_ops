"""运维操作层的模型。

这里只放「操作产生的结果」类数据（分析结果缓存等）；资产本体仍在 assets 应用。
"""

from django.db import models


class InternetAnalysis(models.Model):
    """互联网资产分析结果的缓存。

    分析要从 GSLB 的 WideIP 一路追到 LTM 后端成员，遍历 GTM/LTM 多张表并在内存里
    做关联（见 ``ops/api/analysis.py``），成本不低；而结果变化并不频繁。所以只在
    手动触发「立即分析」时重算并写这张表，平时查询直接读缓存。

    每台 GSLB 设备只保留一份最新结果，重复分析即覆盖。
    """

    device = models.ForeignKey(
        "assets.Device",
        on_delete=models.CASCADE,
        related_name="internet_analyses",
        verbose_name="GSLB 设备",
    )
    result = models.JSONField(default=dict, verbose_name="分析结果")
    analyzed_at = models.DateTimeField(auto_now=True, verbose_name="分析时间")
    duration_ms = models.PositiveIntegerField(default=0, verbose_name="分析耗时(毫秒)")

    class Meta:
        verbose_name = "互联网资产分析缓存"
        verbose_name_plural = verbose_name
        constraints = (models.UniqueConstraint(fields=["device"], name="uni_internet_analysis_device"),)
        ordering = ("-analyzed_at", "-pk")

    def __str__(self):
        return f"{self.device.hostname} 分析结果"
