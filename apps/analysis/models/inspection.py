"""巡检模型：设备 CPU / 内存日指标、接口带宽日指标、巡检批次、带宽采集目标。

每天一行、按 ``date`` 独立保留（滚存由 ``analysis.prune_inspection`` 清理）；同一天
重跑走 upsert，不产生重复。设计链路见 handbook/analysis.md「巡检」。
"""

from datetime import time

from django.db import models


class InspectionConfig(models.Model):
    """巡检全局配置（单例）：调度时间点 + 每次采集的时间范围。

    beat 每分钟触发 ``analysis.inspection_tick``，到点且 ``last_dispatch_date`` 不是今天
    才投递，避免同一分钟 / 同一天重复采集。时间范围按自然日内的 ``[开始, 结束]`` 取样本。
    """

    schedule_hour = models.PositiveSmallIntegerField(default=23, verbose_name="巡检时间点-时")
    schedule_minute = models.PositiveSmallIntegerField(default=50, verbose_name="巡检时间点-分")
    window_start = models.TimeField(default=time(0, 0), verbose_name="巡检时间范围-开始")
    window_end = models.TimeField(default=time(23, 59), verbose_name="巡检时间范围-结束")
    last_dispatch_date = models.DateField(null=True, blank=True, verbose_name="最近投递日期")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "巡检配置"
        verbose_name_plural = verbose_name

    @classmethod
    def load(cls) -> "InspectionConfig":
        """取单例（pk=1），不存在时用默认值创建。"""
        config, _ = cls.objects.get_or_create(pk=1)
        return config

    def __str__(self):
        return f"{self.schedule_hour:02d}:{self.schedule_minute:02d} {self.window_start}-{self.window_end}"


class InspectionDeviceTarget(models.Model):
    """设备巡检对象：逐台 Zabbix 主机，启用的参与 CPU / 内存采集。

    与 ``InspectionTarget``（接口带宽）并列；两者都由 admin 或「巡检」页维护，
    调度任务读取后作为参数传给 ingest，ingest 不反向 import 本表。
    """

    host = models.CharField(max_length=128, unique=True, verbose_name="Zabbix 主机名")
    enabled = models.BooleanField(default=True, verbose_name="启用")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "设备巡检对象"
        verbose_name_plural = verbose_name
        ordering = ("host",)

    def __str__(self):
        return self.host


class InspectionTarget(models.Model):
    """接口带宽巡检目标：采集器的输入配置，admin 或「巡检」页维护。

    与 ``LinkTarget`` 同类职责：执行采集的 ingest 任务是按任务参数拿到这份清单的
    （``analysis → ingest`` 正向），ingest 不反向 import 本表。
    """

    host = models.CharField(max_length=128, verbose_name="Zabbix 主机名")
    ifname = models.CharField(max_length=128, verbose_name="接口名")
    itemids = models.JSONField(default=list, verbose_name="监控项ID缓存")
    enabled = models.BooleanField(default=True, verbose_name="启用")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "巡检带宽目标"
        verbose_name_plural = verbose_name
        constraints = (models.UniqueConstraint(fields=["host", "ifname"], name="uni_inspection_target"),)
        ordering = ("host", "ifname")

    def __str__(self):
        return f"{self.host}@{self.ifname}"


class DeviceMetricDaily(models.Model):
    """设备 CPU / 内存日聚合：``(date, host)`` 唯一，数值 NULL 表示当天无样本。"""

    date = models.DateField(verbose_name="业务日期")
    host = models.CharField(max_length=128, verbose_name="Zabbix 主机名")
    cpu_avg = models.FloatField(null=True, verbose_name="CPU 日均")
    cpu_max = models.FloatField(null=True, verbose_name="CPU 峰值")
    memory_avg = models.FloatField(null=True, verbose_name="内存日均")
    memory_max = models.FloatField(null=True, verbose_name="内存峰值")
    payload = models.JSONField(default=dict, verbose_name="溯源信息")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="落库时间")

    class Meta:
        verbose_name = "设备巡检日指标"
        verbose_name_plural = verbose_name
        constraints = (models.UniqueConstraint(fields=["date", "host"], name="uni_inspection_device_day"),)
        indexes = (models.Index(fields=["date"], name="idx_inspection_device_date"),)
        ordering = ("-date", "host")

    def __str__(self):
        return f"{self.host}@{self.date}"


class InterfaceMetricDaily(models.Model):
    """接口带宽日聚合：``(date, host, ifname)`` 唯一。

    出入方向分带宽（bps）与使用率（%）两组，各存日均与峰值；方向识别不出的监控项
    不进这些字段，原文聚合留在 ``payload.unclassified`` 供溯源。
    """

    date = models.DateField(verbose_name="业务日期")
    host = models.CharField(max_length=128, verbose_name="Zabbix 主机名")
    ifname = models.CharField(max_length=128, verbose_name="接口名")
    in_bps_avg = models.FloatField(null=True, verbose_name="入向带宽日均")
    in_bps_max = models.FloatField(null=True, verbose_name="入向带宽峰值")
    out_bps_avg = models.FloatField(null=True, verbose_name="出向带宽日均")
    out_bps_max = models.FloatField(null=True, verbose_name="出向带宽峰值")
    in_usage_avg = models.FloatField(null=True, verbose_name="入向使用率日均")
    in_usage_max = models.FloatField(null=True, verbose_name="入向使用率峰值")
    out_usage_avg = models.FloatField(null=True, verbose_name="出向使用率日均")
    out_usage_max = models.FloatField(null=True, verbose_name="出向使用率峰值")
    payload = models.JSONField(default=dict, verbose_name="溯源信息")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="落库时间")

    class Meta:
        verbose_name = "接口巡检日指标"
        verbose_name_plural = verbose_name
        constraints = (models.UniqueConstraint(fields=["date", "host", "ifname"], name="uni_inspection_iface_day"),)
        indexes = (models.Index(fields=["date"], name="idx_inspection_iface_date"),)
        ordering = ("-date", "host", "ifname")

    def __str__(self):
        return f"{self.host}@{self.ifname} {self.date}"


class InspectionRun(models.Model):
    """巡检批次：一天一条，记录成功/失败与采集条数，作为数据新鲜度来源。"""

    STATUS_CHOICES = (
        ("success", "成功"),
        ("failed", "失败"),
    )

    date = models.DateField(unique=True, verbose_name="业务日期")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, verbose_name="结果")
    device_count = models.PositiveIntegerField(default=0, verbose_name="设备条数")
    interface_count = models.PositiveIntegerField(default=0, verbose_name="接口条数")
    error = models.TextField(blank=True, default="", verbose_name="错误信息")
    started_at = models.DateTimeField(verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="结束时间")

    class Meta:
        verbose_name = "巡检批次"
        verbose_name_plural = verbose_name
        ordering = ("-date",)

    def __str__(self):
        return f"{self.date} {self.status}"
