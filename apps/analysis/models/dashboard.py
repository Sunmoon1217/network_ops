"""Dashboard 供数模型：当前值读模型 / 时序样本 / 工单实体 / 采集批次 / 链路目标。

分工（依赖方向 ``analysis → ingest → assets`` 单向）：

- ``ingest/collectors/`` 定义采集方法**与 Celery 采集任务**（``@shared_task`` +
  ``asyncio.run``），产出普通 dict / list；任务是采集器的一部分，归属 ingest，
  **不 import 本模块、不碰数据库**；
- 采集任务结束时按 ``settings.DASHBOARD_WRITE_TASK`` 的**任务名字符串**
  ``current_app.send_task(...)`` 把结果投递给 analysis 的写库任务——沿用
  ``ingest/access_flow_trigger.py`` 的接缝（``tests/ingest/test_access_flow_trigger.py``
  守着「投递侧不 import analysis」这条边界）；
- ``analysis/tasks.py`` 的写库任务消费 payload，同步 upsert 到下列表（**唯一写入口**）；
- ``analysis/api/dashboard.py`` 只读，把表数据组装成旧 dashboard 前端的
  ``DashboardData[]`` 形状（``value`` 标量 + ``list_value`` 数组）。

``DashboardMetric`` 保留前端契约的双列，而不是合并成一个 JSON 字段：大屏各卡片按
``name`` 过滤后分别读 ``value`` / ``list_value.length`` / ``list_value[0]``，单列会让读
接口多一层易错的拆分映射。``value`` 用 JSONField 存标量以保住 ``string | number`` 类型
（CharField 会把数字变成字符串）。

时序另立 ``MetricSample``：旧项目把时间编码进 ``name``（``bandwidth_HH:MM``）、把整条
时间轴塞进 ``list_value``，无法按时间范围查询与清理；这里时间独立成列，补历史就是
upsert 同一个 ``sampled_at``，3 小时折线由 API 聚合回 EAV 行视图。
"""

from django.db import models


class DashboardMetric(models.Model):
    """当前值：一个 ``(panel, group, name)`` 一行，重复采集即覆盖。

    三键全非空且唯一（``NULL`` 不参与唯一约束，理由见 ``AccessFlow`` 注释）；写入用
    ``update_or_create`` / ``bulk_create(update_conflicts=True, ...)``，对应旧项目
    SQLAlchemy 的 ``session.merge`` —— Django 没有 merge，不带 pk 直接 save 是 INSERT。
    """

    PANEL_CHOICES = (
        ("statusbar", "状态栏"),
        ("devicestatus", "设备状态"),
        ("link", "链路"),
        ("slb", "SLB"),
        ("inspection", "巡检"),
        ("itsmtask", "工单"),
    )

    panel = models.CharField(max_length=32, choices=PANEL_CHOICES, verbose_name="面板")
    group = models.CharField(max_length=64, verbose_name="分组")
    name = models.CharField(max_length=128, verbose_name="指标名")
    value = models.JSONField(null=True, blank=True, verbose_name="标量值")
    list_value = models.JSONField(default=list, verbose_name="列表值")
    sampled_at = models.DateTimeField(null=True, blank=True, verbose_name="数据源时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="落库时间")

    class Meta:
        verbose_name = "大屏指标"
        verbose_name_plural = verbose_name
        constraints = (models.UniqueConstraint(fields=["panel", "group", "name"], name="uni_dashboard_metric_key"),)
        indexes = (models.Index(fields=["panel", "group"], name="idx_dashboard_metric_screen"),)
        ordering = ("panel", "group", "name")

    def __str__(self):
        return f"{self.panel}/{self.group}/{self.name}"


class MetricSample(models.Model):
    """时序点：链路带宽 / 设备 CPU、内存，一行一个链路（或主机）一个采样点。

    唯一键含 ``sampled_at``：同一时间点重跑不产生重复，也满足将来转 TimescaleDB
    hypertable 时「唯一索引必须包含分区列」的要求。``value`` 为 NULL 表示采集失败或
    无可用数值，不用 0 伪装（0 会污染折线与峰值）。
    """

    KIND_CHOICES = (
        ("link_bandwidth", "链路带宽"),
        ("device_cpu", "CPU"),
        ("device_mem", "内存"),
        ("inspection", "巡检"),
    )

    kind = models.CharField(max_length=16, choices=KIND_CHOICES, verbose_name="指标类型")
    scope = models.CharField(max_length=64, verbose_name="范围")  # ipv4 / fwlink / 设备类型 slug
    subject = models.CharField(max_length=128, verbose_name="主体")  # 链路名 / 主机名
    metric_key = models.CharField(max_length=128, blank=True, default="", verbose_name="监控项标识")
    value = models.FloatField(null=True, verbose_name="数值")
    payload = models.JSONField(default=dict, verbose_name="溯源信息")
    sampled_at = models.DateTimeField(verbose_name="采样时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "大屏时序样本"
        verbose_name_plural = verbose_name
        constraints = (
            models.UniqueConstraint(
                fields=["kind", "scope", "subject", "metric_key", "sampled_at"],
                name="uni_dashboard_sample_key",
            ),
        )
        indexes = (
            models.Index(fields=["kind", "sampled_at"], name="idx_dashboard_sample_time"),
            models.Index(fields=["kind", "scope", "subject", "-sampled_at"], name="idx_dashboard_sample_subject"),
        )
        ordering = ("sampled_at", "kind", "scope", "subject")

    def __str__(self):
        return f"{self.kind}/{self.scope}/{self.subject}@{self.sampled_at:%H:%M}"


class ItsmCase(models.Model):
    """工单实体：外部接口每次返回全量快照，用 ``last_seen_at`` 判定消失的工单。

    不物理删除消失的工单（保留历史）：采集批次结束时把 ``last_seen_at < 批次开始``
    的行置为 ``is_active=False``；大屏 count 用 ``is_active`` 过滤，替换旧代码里恒为
    100.0 的假成功率。``raw`` 保留外部接口原字段（前端还要 zhixing / shijian / status，
    ``ExtraModel`` 的 ``extra="allow"`` 能把它们透传过来）。
    """

    case_no = models.CharField(max_length=64, unique=True, verbose_name="工单号")
    title = models.CharField(max_length=255, verbose_name="标题")
    applicant = models.CharField(max_length=128, blank=True, default="", verbose_name="申请人")
    raw = models.JSONField(default=dict, verbose_name="外部原始字段")
    is_active = models.BooleanField(default=True, verbose_name="在最新快照中")
    first_seen_at = models.DateTimeField(auto_now_add=True, verbose_name="首次采集时间")
    last_seen_at = models.DateTimeField(auto_now=True, verbose_name="最后采集时间")

    class Meta:
        verbose_name = "自动化工单"
        verbose_name_plural = verbose_name
        ordering = ("-last_seen_at", "-pk")

    def __str__(self):
        return f"{self.case_no} {self.title}"


class CollectionRun(models.Model):
    """采集批次：大屏数据新鲜度与失败审计（替代旧代码 ``except: return None``）。"""

    SOURCE_CHOICES = (
        ("zabbix", "Zabbix"),
        ("autotask", "ITSM/巡检"),
        ("derived", "派生聚合"),
    )
    STATUS_CHOICES = (
        ("success", "成功"),
        ("failed", "失败"),
    )

    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, verbose_name="数据源")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, verbose_name="结果")
    item_count = models.PositiveIntegerField(default=0, verbose_name="采集条数")
    error = models.TextField(blank=True, default="", verbose_name="错误信息")
    started_at = models.DateTimeField(verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="结束时间")

    class Meta:
        verbose_name = "采集批次"
        verbose_name_plural = verbose_name
        ordering = ("-started_at", "-pk")

    def __str__(self):
        return f"{self.source} {self.status} @{self.started_at:%Y-%m-%d %H:%M}"


class LinkTarget(models.Model):
    """链路采集目标配置：替代旧 ``link_dict`` 的硬编码与运行期就地写 ``itemids``。

    它是采集器的输入配置，执行采集的 ingest 任务不能反向 import 本表：要么由
    analysis 侧的调度任务读出后**作为任务参数**投递给 ingest（``analysis → ingest``
    正向），要么把这份配置留在 ingest 侧（常量 / 自己的表）。
    """

    link_group = models.CharField(max_length=32, verbose_name="链路组")  # ipv4 / ipv6 / fwlink
    link_name = models.CharField(max_length=64, verbose_name="链路名")
    host = models.CharField(max_length=128, verbose_name="Zabbix 主机名")
    ifname = models.CharField(max_length=128, verbose_name="接口名")
    itemids = models.JSONField(default=list, verbose_name="监控项ID缓存")
    enabled = models.BooleanField(default=True, verbose_name="启用")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "链路采集目标"
        verbose_name_plural = verbose_name
        constraints = (models.UniqueConstraint(fields=["link_group", "link_name"], name="uni_dashboard_link_target"),)
        ordering = ("link_group", "link_name")

    def __str__(self):
        return f"{self.link_group}/{self.link_name} @{self.host}"
