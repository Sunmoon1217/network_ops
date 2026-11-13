"""统一配置项体系（T1）：CI 主表与 4 类 CI 专属扩展（1 类实物资产 + 3 类软资产）。

从单文件 models.py 拆出；``__init__.py`` 显式 re-export，保持
``from assets.models import ConfigurationItem`` 等导入路径与 ``app_label`` 不变，
历史迁移 0031_ci_foundation 不受影响。
"""

import uuid

from django.db import models

# 统一配置项体系（T1）：现阶段只做信息录入与查询，不含生命周期管理


class CIType:
    """资产类型标识（字符串常量，刻意不用 Enum）。

    ``Enum`` 成员与同值字符串的哈希不同，作为 dict 键会查不到（见
    ``llmtools.domains.assets.nodes.NodeType`` 的同一条坑）。

    **只登记资产**，按 ``PHYSICAL_TYPES`` / ``SOFT_TYPES`` 分两类：
    实物资产有物理实体；软资产的身份来自自身全局标识，设备只是部署位置之一。

    不进本清单的三类：
    - **设备内部功能 / 状态**：``Vlan`` / ``Vrf`` / ``Interface`` / ``Route`` / ``ArpMac``
      及 24 个 ``ConfigBase`` 子类的其余部分。身份是 ``(设备, 名称/编号)``，
      强依赖所属设备、跨设备无独立身份，只作资产明细 / 证据。
    - **DCIM 位置维度**：``DataCenter`` / ``Room`` / ``Cabinet`` 算位置，不算资产。
    - **关系 / 元数据 / 日志**：``DeviceGroup*``、T3 关系表、字典表、时序日志等。

    ``DOMAIN`` / ``LOAD_BALANCER_SERVICE`` 是**软资产类型**，不是配置模型名：
    域名 / 负载均衡服务资产由 T4 从 ``GtmWideip`` / ``LtmVirtualServer`` 配置行
    按归一键（FQDN / ``VIP#port``）跨设备归并生成，配置行本身不是资产实体。
    """

    # 实物资产
    DEVICE = "device"
    PHYSICAL_SERVER = "physical_server"

    # 软资产
    VIRTUAL_MACHINE = "virtual_machine"
    DATABASE_INSTANCE = "database_instance"
    APPLICATION_SERVICE = "application_service"
    SUBNET = "subnet"
    IP_ADDRESS = "ip_address"
    DOMAIN = "domain"
    LOAD_BALANCER_SERVICE = "load_balancer_service"


#: 资产大类分组（零迁移的常量分组，不落 ``asset_kind`` 字段）
PHYSICAL_TYPES = frozenset({CIType.DEVICE, CIType.PHYSICAL_SERVER})
SOFT_TYPES = frozenset(
    {
        CIType.VIRTUAL_MACHINE,
        CIType.DATABASE_INSTANCE,
        CIType.APPLICATION_SERVICE,
        CIType.SUBNET,
        CIType.IP_ADDRESS,
        CIType.DOMAIN,
        CIType.LOAD_BALANCER_SERVICE,
    }
)

CI_TYPE_CHOICES = (
    (CIType.DEVICE, "网络设备"),
    (CIType.PHYSICAL_SERVER, "物理机"),
    (CIType.VIRTUAL_MACHINE, "虚拟机"),
    (CIType.DATABASE_INSTANCE, "数据库实例"),
    (CIType.APPLICATION_SERVICE, "应用服务"),
    (CIType.SUBNET, "网段"),
    (CIType.IP_ADDRESS, "IP 地址"),
    (CIType.DOMAIN, "域名"),
    (CIType.LOAD_BALANCER_SERVICE, "负载均衡服务"),
)


def _new_ci_id() -> str:
    """跨类型稳定的 CI 标识：短、无特殊字符、可直接写进 Zabbix 主机标签（T15 纳管锚点）。

    不带类型前缀——类型在 ``ci_type`` 字段里，纳管时按它路由实例即可；把类型塞进
    标识反而会在类型改名 / 归并时破坏稳定性。
    """
    return f"CI-{uuid.uuid4().hex[:12]}"


class ConfigurationItem(models.Model):
    """统一配置项主表：跨类型的身份 + 公共属性 + 查询索引。

    刻意**不继承** ``ConfigBase``：``purge_configs`` 靠 ``ConfigBase.__subclasses__()``
    枚举清理配置解析产物，CI 是人工录入 / Excel 导入维护的资产台账，不能被一并清掉。

    ``ci_id`` 生成后永不改（T15 自动纳管会把它写进 Zabbix 主机标签，改名等于锚点失效）；
    ``monitor_status`` 是 T15 状态回写的**预留落点**，与业务状态分离，现阶段只是空字段，
    不接任何回写 / 对账逻辑。公共属性上收到本表，各类型专属属性留 ``_CIExtension`` 子类。
    """

    ci_id = models.CharField(max_length=64, unique=True, editable=False, verbose_name="CI 标识")
    ci_type = models.CharField(max_length=32, choices=CI_TYPE_CHOICES, verbose_name="CI 类型")
    name = models.CharField(max_length=255, verbose_name="名称")
    description = models.TextField(blank=True, default="", verbose_name="描述")
    tags = models.JSONField(default=list, blank=True, verbose_name="标签")
    monitor_status = models.CharField(max_length=20, blank=True, default="", verbose_name="监控状态")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "配置项"
        verbose_name_plural = verbose_name
        ordering = ("ci_type", "name", "ci_id")
        indexes = (models.Index(fields=("ci_type", "name"), name="ci_type_name_idx"),)

    def save(self, *args, **kwargs):
        if not self.ci_id:
            self.ci_id = _new_ci_id()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.ci_id} {self.name}"


class _CIExtension(models.Model):
    """CI 专属属性扩展的抽象基类：统一 ``ci`` 关联与「类型必须匹配」校验。

    关系（VM→宿主机、DB→主机等）不在这里建外键，统一归 T3 的关系表；跨类型关联
    走 ``ci_id``，否则每加一类资产都要回改这里的字段。
    """

    EXPECTED_CI_TYPE = ""

    ci = models.OneToOneField(ConfigurationItem, on_delete=models.CASCADE, related_name="%(class)s", verbose_name="配置项")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.ci.ci_type != self.EXPECTED_CI_TYPE:
            raise ValueError(f"{type(self).__name__} 要求 ci_type={self.EXPECTED_CI_TYPE}，收到 {self.ci.ci_type}")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.ci.ci_id} / {self.ci.name}"


class PhysicalServer(_CIExtension):
    """物理机：菜单「资产 → 主机 → 物理机」的录入载体"""

    EXPECTED_CI_TYPE = CIType.PHYSICAL_SERVER

    hostname = models.CharField(max_length=255, blank=True, default="", verbose_name="主机名")
    mgmt_ip = models.GenericIPAddressField(blank=True, null=True, verbose_name="管理 IP")
    cpu_cores = models.PositiveIntegerField(null=True, blank=True, verbose_name="CPU 核数")
    memory_gb = models.PositiveIntegerField(null=True, blank=True, verbose_name="内存(GB)")
    os = models.CharField(max_length=100, blank=True, default="", verbose_name="操作系统")
    serial_number = models.CharField(max_length=100, blank=True, default="", verbose_name="序列号")

    class Meta:
        verbose_name = "物理机"
        verbose_name_plural = verbose_name


class VirtualMachine(_CIExtension):
    """虚拟机；宿主机关系归 T3，这里只存名字"""

    EXPECTED_CI_TYPE = CIType.VIRTUAL_MACHINE

    hostname = models.CharField(max_length=255, blank=True, default="", verbose_name="主机名")
    mgmt_ip = models.GenericIPAddressField(blank=True, null=True, verbose_name="管理 IP")
    vcpu = models.PositiveIntegerField(null=True, blank=True, verbose_name="vCPU")
    memory_gb = models.PositiveIntegerField(null=True, blank=True, verbose_name="内存(GB)")
    os = models.CharField(max_length=100, blank=True, default="", verbose_name="操作系统")
    host_name = models.CharField(max_length=255, blank=True, default="", verbose_name="宿主机")

    class Meta:
        verbose_name = "虚拟机"
        verbose_name_plural = verbose_name


class DatabaseInstance(_CIExtension):
    """数据库实例；所属主机关系归 T3"""

    EXPECTED_CI_TYPE = CIType.DATABASE_INSTANCE

    engine = models.CharField(max_length=50, blank=True, default="", verbose_name="引擎")
    version = models.CharField(max_length=50, blank=True, default="", verbose_name="版本")
    port = models.PositiveIntegerField(null=True, blank=True, verbose_name="端口")
    size_gb = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name="容量(GB)")
    host_name = models.CharField(max_length=255, blank=True, default="", verbose_name="所属主机")

    class Meta:
        verbose_name = "数据库实例"
        verbose_name_plural = verbose_name


class ApplicationService(_CIExtension):
    """应用服务：菜单「资产 → 应用服务 → 应用系统」的录入载体"""

    EXPECTED_CI_TYPE = CIType.APPLICATION_SERVICE

    service_type = models.CharField(max_length=50, blank=True, default="", verbose_name="服务类型")
    port = models.PositiveIntegerField(null=True, blank=True, verbose_name="端口")
    url_path = models.CharField(max_length=255, blank=True, default="", verbose_name="访问路径")

    class Meta:
        verbose_name = "应用服务"
        verbose_name_plural = verbose_name
