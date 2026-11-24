"""统一配置项体系（T1）：CI 主表与 4 类 CI 专属扩展（1 类实物资产 + 3 类软资产）。"""

import uuid

from django.db import models


class CIType:
    """资产类型标识（字符串常量，刻意不用 Enum：同值字符串与 Enum 成员哈希不同）。

    **只登记资产**，按 ``PHYSICAL_TYPES`` / ``SOFT_TYPES`` 分组；设备内部配置行、
    DCIM 位置、关系 / 日志都不是资产。分类边界见 handbook/assets.md「资产分类边界」。
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
    """生成 ``CI-<12位hex>``：不透明锚点，不含类型前缀，可直接写进 Zabbix 主机标签。"""
    return f"CI-{uuid.uuid4().hex[:12]}"


class ConfigurationItem(models.Model):
    """统一配置项主表：跨类型身份与公共属性；专属属性留 ``_CIExtension`` 子类。

    ``ci_id`` 创建后永不改；刻意**不继承** ``ConfigBase``（不能被 ``purge_configs`` 清掉）。
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
    """CI 专属属性扩展的抽象基类：统一 ``ci`` 关联，并在 save 时校验类型匹配。"""

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
