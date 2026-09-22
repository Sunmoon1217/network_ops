"""运维操作层（数据采集与解析入库）的模型。

这里只放「操作的产出 / 派生数据」（访问流等）；资产本体仍在 assets 应用。
互联网资产分析缓存已随 analysis 拆分迁走（``analysis.models.InternetAnalysis``）。
"""

from django.contrib.postgres.indexes import GinIndex
from django.db import models


class AccessFlow(models.Model):
    """访问流：一条 (源地址, 目的地址, 服务) 的业务流 + 命中它的全部 (设备, 策略) 上下文。

    由防火墙策略（``assets.Policy`` 的 src/dst/service 三个 M2M）展开而来，
    用于跨设备审计同一条访问流的**遗漏**（该放行没放行）与**多开**（不该放行却放行了）。

    键的形状（九个字段全非空，一起构成唯一约束）：

    - 地址每侧三段：``ip``（GenericIPAddressField，主机地址或网络地址）+ ``prefix``
      （前缀长度：子网=实际值、单 IP=v4 的 32 / v6 的 128、范围与任意=0）+
      ``range_end``（范围结束地址的归一化文本，非范围形态为空串）——四种形态
      （单 IP / 子网 / 范围 / 任意）都装得下，且**不靠 NULL 表达任何语义**
      （NULL 不参与唯一约束，重复行会从那里漏进来；空串与 0 是值，约束始终生效）。
      任意（any）固定归一到 ``0.0.0.0/0``（ip=0.0.0.0, prefix=0），与显式的
      ``0.0.0.0/0`` 子网同键——语义本就相同，聚到一行是期望行为。
    - 服务三段：``protocol``（choices，与 ``Service.protocol`` 同一套，空值归 any）+
      ``port`` / ``port2``（范围结束，非范围为空串；icmp 等无端口时两者皆空）。
    - **不挂外键**：``AddressBook`` / ``Service`` 都按设备隔离（``ConfigBase.device``），
      用外键 id 做键的话同一条访问流会在每台设备各落一行，跨设备聚合的目的就落空了。
      键值全部来自归一化（IPv6 大小写/压缩写法先经 ``ipaddress`` 规整）。

    上下文与冗余：

    - ``contexts`` 用 dict 而不是 list：键是 ``"<device_id>:<policy_pk>"``（策略
      **主键**，不是内容）——同一台设备上内容重复的两条策略会各占一个键、互不覆盖，
      这正是「设备内重复策略 / 多开」审计的数据来源；重放时同键覆盖（幂等），
      ``device_ids`` / ``policy_ids`` 冗余数组天然去重。
    - ``device_ids`` / ``policy_ids`` 是冗余数组，配 GIN 索引回答「这台设备 / 这条
      策略出现在哪些行」（重建时先按设备摘除旧 context、API 按设备过滤）。
    - 不继承 ``ConfigBase``：它是跨设备聚合行，没有归属设备（基类的 device 非空）。
      与 ``InternetAnalysis`` 同属「派生缓存」，由 ``purge_configs`` 显式纳入清理。
    """

    #: 与 assets.Service.protocol 同一套取值（那边是权威；tests/ops/test_policy_expand.py
    #: 有对账测试防两边漂移）。不直接 import Service 是因为 ops.models 加载时 assets
    #: 尚未就绪（INSTALLED_APPS 顺序），choices 只是展示层数据，重复声明最省事。
    PROTOCOL_CHOICES = (
        ("tcp", "TCP"),
        ("udp", "UDP"),
        ("tcp-udp", "TCP/UDP"),
        ("icmp", "ICMP"),
        ("any", "ANY"),
    )

    src_ip = models.GenericIPAddressField(protocol="both", verbose_name="源地址")
    src_prefix = models.PositiveSmallIntegerField(verbose_name="源前缀长度")
    # range_end 存 CharField 而不是 GenericIPAddressField：后者 blank=True 时 Django
    # 强制走 NULL 存储（系统检查 E150），而 NULL 不参与唯一约束，「非范围」的语义
    # 一旦是 NULL，重复行就从这里漏进来了。文本值同样经 ipaddress 归一化，格式可控。
    src_range_end = models.CharField(max_length=45, blank=True, default="", verbose_name="源结束地址")
    dst_ip = models.GenericIPAddressField(protocol="both", verbose_name="目的地址")
    dst_prefix = models.PositiveSmallIntegerField(verbose_name="目的前缀长度")
    dst_range_end = models.CharField(max_length=45, blank=True, default="", verbose_name="目的结束地址")
    protocol = models.CharField(max_length=10, choices=PROTOCOL_CHOICES, verbose_name="协议")
    port = models.CharField(max_length=15, blank=True, default="", verbose_name="起始端口")
    port2 = models.CharField(max_length=15, blank=True, default="", verbose_name="结束端口")

    contexts = models.JSONField(default=dict, verbose_name="命中上下文")
    device_ids = models.JSONField(default=list, verbose_name="设备ID列表")
    policy_ids = models.JSONField(default=list, verbose_name="策略ID列表")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "访问流"
        verbose_name_plural = verbose_name
        constraints = (
            models.UniqueConstraint(
                fields=[
                    "src_ip",
                    "src_prefix",
                    "src_range_end",
                    "dst_ip",
                    "dst_prefix",
                    "dst_range_end",
                    "protocol",
                    "port",
                    "port2",
                ],
                name="uni_accessflow_key",
            ),
        )
        indexes = (
            GinIndex(fields=["device_ids"], name="gin_accessflow_device_ids"),
            GinIndex(fields=["policy_ids"], name="gin_accessflow_policy_ids"),
        )
        ordering = ("-updated_at", "-pk")

    def __str__(self):
        return f"{self.src_ip}/{self.src_prefix} -> {self.dst_ip}/{self.dst_prefix} {self._service_label()}"

    def _service_label(self) -> str:
        if self.port:
            label = f"{self.protocol}/{self.port}" + (f"-{self.port2}" if self.port2 else "")
        else:
            label = self.protocol
        return label
