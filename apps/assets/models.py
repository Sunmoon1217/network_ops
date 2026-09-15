import re
from typing import TYPE_CHECKING

from django.db import models
from django.db.models import QuerySet


class SecurityZone(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name="安全区名称")
    color = models.CharField(max_length=7, default="#3b82f6", verbose_name="标识颜色")
    description = models.TextField(blank=True, default="", verbose_name="描述")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "安全区"
        verbose_name_plural = verbose_name
        ordering = ("name",)

    def __str__(self):
        return self.name


class DataCenter(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="数据中心名称")
    address = models.CharField(max_length=255, blank=True, default="", verbose_name="地址")
    contact = models.CharField(max_length=100, blank=True, default="", verbose_name="联系人")
    phone = models.CharField(max_length=50, blank=True, default="", verbose_name="联系电话")
    remark = models.TextField(blank=True, default="", verbose_name="备注")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "数据中心"
        verbose_name_plural = verbose_name
        ordering = ("name",)

    def __str__(self):
        return self.name


class Room(models.Model):
    name = models.CharField(max_length=100, verbose_name="机房名称")
    datacenter = models.ForeignKey(
        DataCenter, on_delete=models.CASCADE, related_name="rooms", verbose_name="所属数据中心"
    )
    contact = models.CharField(max_length=100, blank=True, default="", verbose_name="联系人")
    remark = models.TextField(blank=True, default="", verbose_name="备注")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "机房"
        verbose_name_plural = verbose_name
        ordering = ("datacenter", "name")
        constraints = (models.UniqueConstraint(fields=["datacenter", "name"], name="uni_room_datacenter_name"),)

    def __str__(self):
        return f"{self.datacenter.name} / {self.name}"


class Cabinet(models.Model):
    STATUS_CHOICES = [
        ("active", "使用中"),
        ("reserved", "预留"),
        ("maintenance", "维护中"),
        ("decommissioned", "已下架"),
    ]

    name = models.CharField(max_length=50, verbose_name="机柜编号")
    row = models.CharField(max_length=20, blank=True, default="", verbose_name="排")
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="cabinets", verbose_name="所属机房")
    total_u = models.PositiveIntegerField(default=42, verbose_name="总U数")
    power_capacity = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="额定功率(kW)"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active", verbose_name="状态")
    remark = models.TextField(blank=True, default="", verbose_name="备注")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "机柜"
        verbose_name_plural = verbose_name
        ordering = ("room", "row", "name")
        constraints = (models.UniqueConstraint(fields=["room", "name"], name="uni_cabinet_room_name"),)

    def __str__(self):
        return f"{self.room} / {self.name}"

    def save(self, *args, **kwargs):
        if not self.row and self.name:
            match = re.match(r"^([A-Za-z]+)", self.name)
            if match:
                self.row = match.group(1).upper()
        super().save(*args, **kwargs)


class Vendor(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name="厂商名称")
    name_en = models.CharField(max_length=100, blank=True, default="", verbose_name="英文名")
    abbr = models.CharField(max_length=20, blank=True, default="", verbose_name="缩写")

    class Meta:
        verbose_name = "设备厂商"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class DeviceModel(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="设备型号")
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="device_models", verbose_name="所属厂商")

    class Meta:
        verbose_name = "设备型号"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.vendor.name} {self.name}"


class Device(models.Model):
    DEVICE_TYPE_CHOICES = (
        ("firewall", "防火墙"),
        ("switch", "交换机"),
        ("loadbalancer", "负载均衡"),
        ("router", "路由器"),
        ("server", "服务器"),
        ("dns", "域名解析"),
        ("dwdm", "波分复用"),
        ("internalac", "上网行为管理"),
        ("wirelessac", "无线控制器"),
    )

    hostname = models.CharField(max_length=100, unique=True, verbose_name="主机名")
    device_model = models.ForeignKey(
        DeviceModel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="devices",
        verbose_name="设备型号",
    )
    device_type = models.CharField(max_length=50, choices=DEVICE_TYPE_CHOICES, verbose_name="设备类型")
    idc = models.ForeignKey(
        DataCenter,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="devices",
        verbose_name="数据中心",
    )
    cabinet = models.ForeignKey(
        Cabinet,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="devices",
        verbose_name="所属机柜",
    )
    security_zone = models.ForeignKey(
        SecurityZone,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="devices",
        verbose_name="安全区",
    )
    u_position = models.PositiveIntegerField(blank=True, null=True, verbose_name="起始U位")
    height = models.PositiveIntegerField(default=1, verbose_name="设备高度(U)")
    ip_address = models.CharField(max_length=50, blank=True, default="", verbose_name="管理IP")
    remark = models.TextField(blank=True, default="", verbose_name="备注")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "网络设备"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.hostname


class DeviceConnection(models.Model):
    CONNECTION_TYPE_CHOICES = (
        ("netmiko", "Netmiko"),
        ("napalm", "NAPALM"),
        ("paramiko", "Paramiko"),
        ("ssh", "SSH"),
    )

    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        related_name="connections",
        null=True,
        blank=True,
        verbose_name="关联设备",
    )
    address = models.GenericIPAddressField(blank=True, null=True, verbose_name="连接地址")
    connection_type = models.CharField(
        max_length=20, choices=CONNECTION_TYPE_CHOICES, default="napalm", verbose_name="连接类型"
    )
    driver = models.CharField(max_length=50, blank=True, default="", verbose_name="驱动/平台")
    port = models.PositiveIntegerField(default=22, verbose_name="端口")
    account_type = models.CharField(
        max_length=20,
        choices=[("admin", "管理员"), ("operator", "操作员"), ("readonly", "只读用户")],
        default="admin",
        verbose_name="账号类型",
    )
    username = models.CharField(max_length=100, verbose_name="用户名")
    password = models.CharField(max_length=255, verbose_name="密码")
    enable_password = models.CharField(max_length=255, blank=True, default="", verbose_name="Enable密码")
    timeout = models.PositiveIntegerField(default=30, verbose_name="连接超时(秒)")
    enabled = models.BooleanField(default=True, verbose_name="启用")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "设备连接信息"
        verbose_name_plural = verbose_name
        constraints = (
            models.UniqueConstraint(fields=["device", "account_type"], name="uni_deviceconn_device_account"),
        )

    def __str__(self):
        return f"{self.device.hostname} ({self.connection_type})"

    def get_address(self) -> str:
        """获取连接地址（优先级：连接地址 > 设备地址）"""
        if self.address:
            return self.address
        if self.device:
            return self.device.hostname
        return ""


class DeviceConfig(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="configs", verbose_name="关联设备")
    git_commit_hash = models.CharField(max_length=40, verbose_name="Git Commit Hash")
    config_json = models.JSONField(blank=True, null=True, verbose_name="解析后的配置数据")
    parse_duration = models.FloatField(null=True, blank=True, verbose_name="解析耗时(秒)")
    collected_at = models.DateTimeField(auto_now_add=True, verbose_name="采集时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "设备配置"
        verbose_name_plural = verbose_name
        ordering = ("-collected_at",)

    def __str__(self):
        return f"{self.device.hostname} - {self.collected_at}"


class ConfigBase(models.Model):
    """配置模型基类"""

    device = models.ForeignKey(Device, on_delete=models.CASCADE, verbose_name="关联设备")
    is_active = models.BooleanField(default=True, verbose_name="是否生效")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        abstract = True


class Vlan(models.Model):
    """VLAN"""

    device = models.ForeignKey(
        Device, on_delete=models.CASCADE, related_name="vlans", null=True, blank=True, verbose_name="所属设备"
    )
    vid = models.PositiveIntegerField(verbose_name="VLAN ID")
    name = models.CharField(max_length=100, blank=True, default="", verbose_name="VLAN名称")
    description = models.CharField(max_length=255, blank=True, default="", verbose_name="描述")

    class Meta:
        verbose_name = "VLAN"
        verbose_name_plural = verbose_name
        ordering = ("vid",)
        constraints = (models.UniqueConstraint(fields=["device", "vid"], name="uni_vlan_device_vid"),)

    def __str__(self):
        prefix = f"{self.device.hostname} - " if self.device else ""
        return f"{prefix}VLAN {self.vid}" + (f" ({self.name})" if self.name else "")


class Vrf(ConfigBase):
    """VRF"""

    name = models.CharField(max_length=255, verbose_name="名称")
    rd = models.CharField(max_length=50, blank=True, default="", verbose_name="RD")
    description = models.TextField(blank=True, default="", verbose_name="描述")

    class Meta:
        verbose_name = "VRF"
        verbose_name_plural = verbose_name
        constraints = (models.UniqueConstraint(fields=["device", "name"], name="uni_vrf_device_name"),)

    def __str__(self):
        return f"{self.device.hostname} / {self.name}"


class Interface(ConfigBase):
    """网络接口"""

    MODE_CHOICES = (
        ("layer3", "三层接口"),
        ("access", "Access"),
        ("hybrid", "Hybrid"),
        ("trunk", "Trunk"),
    )

    interface = models.CharField(max_length=255, verbose_name="接口名")
    description = models.CharField(max_length=255, null=True, verbose_name="描述")
    enabled = models.BooleanField(default=False, verbose_name="启用")
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, null=True, blank=True, verbose_name="接口模式")
    vlans = models.JSONField(default=dict, blank=True, verbose_name="VLAN配置")
    vrf = models.ForeignKey(
        Vrf, on_delete=models.SET_NULL, null=True, blank=True, related_name="interfaces", verbose_name="VRF"
    )
    type = models.CharField(max_length=255, null=True, verbose_name="接口类型")
    combo_type = models.CharField(max_length=255, null=True, verbose_name="Combo类型")
    ip_address = models.CharField(max_length=255, null=True, verbose_name="IP地址")
    subnet_mask = models.CharField(max_length=255, null=True, verbose_name="子网掩码")

    class Meta:
        verbose_name = "网络接口"
        verbose_name_plural = verbose_name
        constraints = (models.UniqueConstraint(fields=["device", "interface"], name="uni_device_interface"),)

    def __str__(self):
        return f"{self.device.hostname} / {self.interface}"


class DeviceAccount(ConfigBase):
    """设备管理用户（从配置解析）"""

    username = models.CharField(max_length=100, verbose_name="用户名")
    auth_type = models.CharField(
        max_length=20,
        choices=[
            ("password", "密码认证"),
            ("ssh-key", "SSH密钥"),
            ("both", "双因素认证"),
        ],
        default="password",
        verbose_name="认证方式",
    )
    privilege = models.CharField(
        max_length=20,
        choices=[
            ("admin", "管理员"),
            ("operator", "操作员"),
            ("readonly", "只读用户"),
        ],
        default="admin",
        verbose_name="权限级别",
    )
    enabled = models.BooleanField(default=True, verbose_name="启用")
    description = models.CharField(max_length=255, blank=True, default="", verbose_name="描述")

    class Meta:
        verbose_name = "设备账号"
        verbose_name_plural = verbose_name
        constraints = (
            models.UniqueConstraint(fields=["device", "username"], name="uni_deviceaccount_device_username"),
        )

    def __str__(self):
        return f"{self.device.hostname} / {self.username}"


class SnmpConfig(models.Model):
    """SNMP配置基线"""

    device = models.OneToOneField(Device, on_delete=models.CASCADE, related_name="snmp_config", verbose_name="关联设备")
    version = models.CharField(
        max_length=10, choices=[("v1", "v1"), ("v2c", "v2c"), ("v3", "v3")], default="v2c", verbose_name="SNMP版本"
    )
    community_read = models.CharField(max_length=100, blank=True, default="", verbose_name="读社区字符串")
    community_write = models.CharField(max_length=100, blank=True, default="", verbose_name="写社区字符串")
    port = models.PositiveIntegerField(default=161, verbose_name="监听端口")
    trap_enabled = models.BooleanField(default=False, verbose_name="启用Trap")
    trap_server = models.GenericIPAddressField(blank=True, null=True, verbose_name="Trap服务器")
    trap_port = models.PositiveIntegerField(default=162, verbose_name="Trap端口")
    enabled = models.BooleanField(default=True, verbose_name="启用SNMP")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "SNMP配置"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.device.hostname} SNMP"


class NtpConfig(models.Model):
    """NTP配置基线"""

    device = models.OneToOneField(Device, on_delete=models.CASCADE, related_name="ntp_config", verbose_name="关联设备")
    server1 = models.GenericIPAddressField(verbose_name="NTP服务器1")
    server2 = models.GenericIPAddressField(blank=True, null=True, verbose_name="NTP服务器2")
    server3 = models.GenericIPAddressField(blank=True, null=True, verbose_name="NTP服务器3")
    timezone = models.CharField(max_length=50, default="UTC", verbose_name="时区")
    sync_interval = models.PositiveIntegerField(default=64, verbose_name="同步间隔(秒)")
    enabled = models.BooleanField(default=True, verbose_name="启用NTP")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "NTP配置"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.device.hostname} NTP"


class SyslogConfig(models.Model):
    """Syslog配置基线"""

    device = models.OneToOneField(
        Device, on_delete=models.CASCADE, related_name="syslog_config", verbose_name="关联设备"
    )
    server1 = models.GenericIPAddressField(verbose_name="日志服务器1")
    server2 = models.GenericIPAddressField(blank=True, null=True, verbose_name="日志服务器2")
    port = models.PositiveIntegerField(default=514, verbose_name="端口")
    facility = models.CharField(
        max_length=20,
        choices=[(f"local{i}", f"local{i}") for i in range(8)],
        default="local7",
        verbose_name="Facility",
    )
    level = models.CharField(
        max_length=20,
        choices=[
            ("emergency", "emergency"),
            ("alert", "alert"),
            ("critical", "critical"),
            ("error", "error"),
            ("warning", "warning"),
            ("notice", "notice"),
            ("informational", "informational"),
            ("debugging", "debugging"),
        ],
        default="informational",
        verbose_name="日志级别",
    )
    enabled = models.BooleanField(default=True, verbose_name="启用Syslog")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "Syslog配置"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.device.hostname} Syslog"


# ---------------------------------------------------------------------------
# SLB (LTM - Local Traffic Manager)
# ---------------------------------------------------------------------------


class LtmVirtualServer(ConfigBase):
    """虚拟服务器"""

    name = models.CharField(max_length=255, verbose_name="名称")
    vs_address = models.CharField(max_length=255, verbose_name="虚拟地址")
    vs_port = models.CharField(max_length=15, null=True, verbose_name="端口")
    mask = models.CharField(max_length=15, null=True, verbose_name="掩码")
    protocol = models.CharField(max_length=15, null=True, verbose_name="协议")
    source = models.CharField(max_length=15, null=True, verbose_name="源地址")
    snat_type = models.CharField(max_length=255, null=True, verbose_name="SNAT类型")
    pool = models.CharField(max_length=255, null=True, verbose_name="关联池")
    snat_pool = models.CharField(max_length=255, null=True, verbose_name="SNAT池")
    persist = models.CharField(max_length=255, null=True, verbose_name="会话保持")
    profiles = models.JSONField(default=list, verbose_name="Profile列表")
    rules = models.JSONField(default=list, verbose_name="iRule列表")

    class Meta:
        verbose_name = "LTM Virtual Server"
        verbose_name_plural = verbose_name
        constraints = (models.UniqueConstraint(fields=["device", "name"], name="uni_vs_device"),)

    def __str__(self):
        return f"{self.device.hostname} / {self.name}"


class LtmPool(ConfigBase):
    """LTM 池"""

    name = models.CharField(max_length=255, verbose_name="名称")
    mode = models.CharField(max_length=255, verbose_name="负载模式")
    monitors = models.JSONField(default=list, verbose_name="监控列表")

    class Meta:
        verbose_name = "LTM Pool"
        verbose_name_plural = verbose_name
        constraints = (models.UniqueConstraint(fields=["device", "name"], name="uni_pool_device"),)


class LtmPoolMember(models.Model):
    """LTM 池成员"""

    pool_name = models.CharField(max_length=255, blank=True, default="", verbose_name="关联池名称")
    name = models.CharField(max_length=255, verbose_name="成员名称")
    address = models.CharField(max_length=255, verbose_name="地址")

    class Meta:
        verbose_name = "LTM Pool Member"
        verbose_name_plural = verbose_name


class LtmProfile(ConfigBase):
    """LTM Profile"""

    name = models.CharField(max_length=255, verbose_name="名称")
    type = models.CharField(max_length=255, verbose_name="类型")
    raw = models.JSONField(verbose_name="原始配置")

    class Meta:
        verbose_name = "LTM Profile"
        verbose_name_plural = verbose_name


class LtmIRule(ConfigBase):
    """LTM iRule"""

    name = models.CharField(max_length=255, verbose_name="名称")
    raw = models.JSONField(verbose_name="原始配置")

    class Meta:
        verbose_name = "LTM iRule"
        verbose_name_plural = verbose_name


class LtmSNAT(ConfigBase):
    """LTM SNAT"""

    name = models.CharField(max_length=255, verbose_name="名称")
    address = models.CharField(max_length=255, verbose_name="地址")

    class Meta:
        verbose_name = "LTM SNAT"
        verbose_name_plural = verbose_name


class LtmPersist(ConfigBase):
    """LTM 会话保持"""

    name = models.CharField(max_length=255, verbose_name="名称")
    type = models.CharField(max_length=255, verbose_name="类型")
    raw = models.JSONField(verbose_name="原始配置")

    class Meta:
        verbose_name = "LTM Persist"
        verbose_name_plural = verbose_name


# ---------------------------------------------------------------------------
# GSLB (GTM - Global Traffic Manager)
# ---------------------------------------------------------------------------


class GtmDatacenter(ConfigBase):
    """GTM 数据中心"""

    name = models.CharField(max_length=255, verbose_name="名称")

    class Meta:
        verbose_name = "GTM Datacenter"
        verbose_name_plural = verbose_name


class GtmWideip(ConfigBase):
    """GTM Wide IP"""

    name = models.CharField(max_length=255, verbose_name="域名")
    rtype = models.CharField(max_length=255, verbose_name="记录类型")
    lb_mode = models.CharField(max_length=255, verbose_name="负载模式")
    pools = models.JSONField(default=list, null=True, verbose_name="关联池列表")

    class Meta:
        verbose_name = "GTM Wide IP"
        verbose_name_plural = verbose_name
        constraints = (models.UniqueConstraint(fields=["device", "name"], name="uni_wideip_device"),)


class GtmPool(ConfigBase):
    """GTM 池"""

    name = models.CharField(max_length=255, verbose_name="名称")
    lb_mode = models.CharField(max_length=255, default="round-robin", verbose_name="负载模式")
    alternate_mode = models.CharField(max_length=255, default="round-robin", verbose_name="备选模式")
    fallback_mode = models.CharField(max_length=255, default="return-to-dns", verbose_name="回退模式")
    fallback_ip = models.GenericIPAddressField(null=True, verbose_name="回退IP")
    ttl = models.IntegerField(default=30, verbose_name="TTL")
    members = models.JSONField(default=list, verbose_name="成员列表")
    monitor = models.JSONField(default=list, verbose_name="监控列表")

    class Meta:
        verbose_name = "GTM Pool"
        verbose_name_plural = verbose_name


# ---------------------------------------------------------------------------
# Firewall Policy
# ---------------------------------------------------------------------------


class AddressBook(ConfigBase):
    """地址簿"""

    ADDRESS_TYPE_CHOICES = (
        ("host", "主机"),
        ("subnet", "子网"),
        ("range", "地址范围"),
        ("addressbook", "地址簿"),
    )
    name = models.CharField(max_length=255, blank=True, null=True, verbose_name="名称")
    address_type = models.CharField(max_length=20, choices=ADDRESS_TYPE_CHOICES, verbose_name="地址类型")
    ip_address = models.GenericIPAddressField(protocol="both", blank=True, null=True, verbose_name="地址")
    ip_netmask = models.IntegerField(blank=True, null=True, verbose_name="子网掩码")
    ip_start = models.GenericIPAddressField(blank=True, null=True, verbose_name="起始地址")
    ip_end = models.GenericIPAddressField(blank=True, null=True, verbose_name="结束地址")
    parent = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="children", verbose_name="上级地址簿"
    )
    description = models.TextField(blank=True, default="", verbose_name="描述")

    if TYPE_CHECKING:
        from assets.models import AddressBook

        children: QuerySet[AddressBook]

    class Meta:
        verbose_name = "地址簿"
        verbose_name_plural = verbose_name


class Service(ConfigBase):
    """服务"""

    PROTOCOL_CHOICES = (
        ("tcp", "TCP"),
        ("udp", "UDP"),
        ("tcp-udp", "TCP/UDP"),
        ("icmp", "ICMP"),
        ("any", "ANY"),
    )
    name = models.CharField(max_length=255, verbose_name="名称")
    protocol = models.CharField(max_length=10, choices=PROTOCOL_CHOICES, verbose_name="协议")
    port = models.CharField(max_length=255, blank=True, default="", verbose_name="端口")
    port2 = models.CharField(max_length=255, blank=True, default="", verbose_name="结束端口")
    description = models.TextField(blank=True, default="", verbose_name="描述")

    class Meta:
        verbose_name = "服务"
        verbose_name_plural = verbose_name
        constraints = (models.UniqueConstraint(fields=["name"], name="uni_service_name"),)


class Policy(ConfigBase):
    """安全策略"""

    ACTION_CHOICES = (("allow", "允许"), ("deny", "拒绝"))
    policy_id = models.CharField(max_length=50, verbose_name="策略ID")
    order = models.PositiveIntegerField(verbose_name="策略顺序")
    name = models.CharField(max_length=255, verbose_name="策略名称")
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, default="allow", verbose_name="动作")
    enabled = models.BooleanField(default=True, verbose_name="启用")
    source_addresses = models.ManyToManyField(AddressBook, related_name="source_policies", verbose_name="源地址")
    destination_addresses = models.ManyToManyField(
        AddressBook, related_name="destination_policies", verbose_name="目的地址"
    )
    services = models.ManyToManyField(Service, related_name="policies", verbose_name="服务")
    log = models.BooleanField(default=False, verbose_name="记录日志")
    description = models.TextField(blank=True, default="", verbose_name="描述")

    class Meta:
        verbose_name = "安全策略"
        verbose_name_plural = verbose_name
        constraints = (
            models.UniqueConstraint(fields=["device", "policy_id"], name="uni_policy_device_pid"),
            models.UniqueConstraint(fields=["device", "order"], name="uni_policy_device_order"),
        )


class NatRule(ConfigBase):
    """NAT 规则"""

    NAT_TYPE_CHOICES = (
        ("snat", "源地址转换"),
        ("dnat", "目的地址转换"),
        ("dulnat", "双向地址转换"),
    )
    order = models.PositiveIntegerField(verbose_name="规则顺序")
    name = models.CharField(max_length=255, verbose_name="规则名称")
    nat_type = models.CharField(max_length=10, choices=NAT_TYPE_CHOICES, verbose_name="转换类型")
    enabled = models.BooleanField(default=True, verbose_name="启用")
    source_addresses = models.ManyToManyField(AddressBook, related_name="source_nat_rules", verbose_name="匹配源地址")
    destination_addresses = models.ManyToManyField(
        AddressBook, related_name="destination_nat_rules", verbose_name="匹配目的地址"
    )
    services = models.ManyToManyField(Service, related_name="nat_rules", verbose_name="匹配服务")
    translated_source = models.ForeignKey(
        AddressBook,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="translated_src_rules",
        verbose_name="转换后源地址",
    )
    translated_destination = models.ForeignKey(
        AddressBook,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="translated_dst_rules",
        verbose_name="转换后目的地址",
    )
    translated_service = models.ForeignKey(
        Service,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="translated_svc_rules",
        verbose_name="转换后服务",
    )
    description = models.TextField(blank=True, default="", verbose_name="描述")

    class Meta:
        verbose_name = "NAT 规则"
        verbose_name_plural = verbose_name
        constraints = (models.UniqueConstraint(fields=["device", "order"], name="uni_nat_device_order"),)


# ---------------------------------------------------------------------------
# IPAM
# ---------------------------------------------------------------------------


class Tag(models.Model):
    """标签"""

    name = models.CharField(max_length=50, unique=True, verbose_name="标签名称")
    color = models.CharField(max_length=7, default="#3b82f6", verbose_name="颜色")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "标签"
        verbose_name_plural = verbose_name
        ordering = ("name",)

    def __str__(self):
        return self.name


class Subnet(models.Model):
    """网段"""

    network = models.CharField(max_length=18, unique=True, verbose_name="网段 (CIDR)")
    tags = models.ManyToManyField(Tag, blank=True, related_name="subnets", verbose_name="标签")
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children", verbose_name="父网段"
    )
    gateway = models.GenericIPAddressField(null=True, blank=True, verbose_name="默认网关")
    vlan = models.CharField(max_length=20, blank=True, default="", verbose_name="VLAN")
    datacenter = models.ForeignKey(
        DataCenter, on_delete=models.SET_NULL, null=True, blank=True, related_name="subnets", verbose_name="数据中心"
    )
    security_zone = models.ForeignKey(
        SecurityZone, on_delete=models.SET_NULL, null=True, blank=True, related_name="subnets", verbose_name="安全区"
    )
    vrf = models.CharField(max_length=50, blank=True, default="", verbose_name="所属VRF")
    description = models.CharField(max_length=255, blank=True, default="", verbose_name="描述")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    if TYPE_CHECKING:
        from assets.models import IPAddress

        ip_addresses: models.QuerySet[IPAddress]

    class Meta:
        verbose_name = "网段"
        verbose_name_plural = verbose_name
        ordering = ("network",)

    def __str__(self):
        tag_names = ", ".join(self.tags.values_list("name", flat=True))
        return f"{self.network}" + (f" [{tag_names}]" if tag_names else "")

    @property
    def total_ips(self):
        import ipaddress

        try:
            return ipaddress.ip_network(self.network, strict=False).num_addresses - 2
        except Exception:
            return 0

    @property
    def used_ips(self):
        if not self.pk:
            return 0
        return self.ip_addresses.filter(status="used").count()

    @property
    def utilization(self):
        total = self.total_ips
        if total <= 0:
            return 0
        return round(self.used_ips / total * 100, 1)


class IPAddress(models.Model):
    """IP地址"""

    ip_address = models.GenericIPAddressField(unique=True, verbose_name="IP地址")
    subnet = models.ForeignKey(
        Subnet, on_delete=models.SET_NULL, null=True, blank=True, related_name="ip_addresses", verbose_name="所属网段"
    )
    security_zone = models.ForeignKey(
        SecurityZone,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ip_addresses",
        verbose_name="安全区",
    )
    status = models.CharField(
        max_length=20,
        choices=[("used", "已使用"), ("reserved", "预留"), ("available", "可用")],
        default="used",
        verbose_name="状态",
    )
    device = models.ForeignKey(
        Device, on_delete=models.SET_NULL, null=True, blank=True, related_name="ip_addresses", verbose_name="关联设备"
    )
    interface = models.CharField(max_length=100, blank=True, default="", verbose_name="关联接口")
    description = models.CharField(max_length=255, blank=True, default="", verbose_name="描述")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "IP地址"
        verbose_name_plural = verbose_name
        ordering = ("ip_address",)

    def __str__(self):
        return self.ip_address


class Route(models.Model):
    """路由"""

    PROTOCOL_CHOICES = (
        ("static", "静态"),
        ("connected", "直连"),
        ("ospf", "OSPF"),
        ("bgp", "BGP"),
        ("rip", "RIP"),
        ("other", "其他"),
    )

    vrf = models.ForeignKey(Vrf, on_delete=models.CASCADE, related_name="routes", verbose_name="VRF")
    destination = models.CharField(max_length=18, verbose_name="目的网段 (CIDR)")
    nexthop = models.GenericIPAddressField(null=True, blank=True, verbose_name="下一跳地址")
    interface = models.CharField(max_length=255, blank=True, default="", verbose_name="出接口")
    protocol = models.CharField(max_length=20, choices=PROTOCOL_CHOICES, default="static", verbose_name="协议")
    metric = models.PositiveIntegerField(default=0, verbose_name="度量值")
    enabled = models.BooleanField(default=True, verbose_name="启用")
    description = models.TextField(blank=True, default="", verbose_name="描述")

    class Meta:
        verbose_name = "路由"
        verbose_name_plural = verbose_name
        constraints = (models.UniqueConstraint(fields=["vrf", "destination", "nexthop"], name="uni_route_vrf_dst_nh"),)

    def __str__(self):
        return f"{self.destination} → {self.nexthop or self.interface}"


# ---------------------------------------------------------------------------
# 网络拓扑
# ---------------------------------------------------------------------------


class Topology(models.Model):
    """网络拓扑图"""

    name = models.CharField(max_length=100, unique=True, verbose_name="拓扑名称")
    description = models.TextField(blank=True, default="", verbose_name="描述")
    graph_data = models.JSONField(default=dict, verbose_name="图数据", help_text="antv/g6 格式 JSON")
    is_default = models.BooleanField(default=False, verbose_name="默认拓扑")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "网络拓扑"
        verbose_name_plural = verbose_name
        ordering = ("-updated_at",)

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# ARP/MAC 表
# ---------------------------------------------------------------------------


class ArpMac(models.Model):
    """ARP/MAC 地址表"""

    ARP_TYPE_CHOICES = (
        ("dynamic", "动态"),
        ("static", "静态"),
    )
    STATUS_CHOICES = (
        ("normal", "正常"),
        ("aging", "老化中"),
        ("conflict", "冲突"),
    )

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="arp_mac_entries", verbose_name="设备")
    vlan = models.CharField(max_length=50, blank=True, default="", verbose_name="VLAN")
    interface = models.CharField(max_length=255, blank=True, default="", verbose_name="接口")
    ip_address = models.GenericIPAddressField(verbose_name="IP 地址")
    mac_address = models.CharField(max_length=17, verbose_name="MAC 地址")
    vendor = models.CharField(max_length=100, blank=True, default="", verbose_name="厂商")
    arp_type = models.CharField(max_length=20, choices=ARP_TYPE_CHOICES, default="dynamic", verbose_name="ARP 类型")
    learned_at = models.DateTimeField(null=True, blank=True, verbose_name="学习时间")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="normal", verbose_name="状态")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "ARP/MAC"
        verbose_name_plural = verbose_name
        ordering = ("-updated_at",)
        constraints = (
            models.UniqueConstraint(fields=["device", "ip_address", "mac_address"], name="uni_arpmac_device_ip_mac"),
        )

    def __str__(self):
        return f"{self.ip_address} → {self.mac_address}"


# ---------------------------------------------------------------------------
# 子网使用率趋势
# ---------------------------------------------------------------------------


class SubnetUsageLog(models.Model):
    """子网 IP 使用率快照（定时记录）"""

    subnet = models.ForeignKey(Subnet, on_delete=models.CASCADE, related_name="usage_logs", verbose_name="网段")
    total_ips = models.PositiveIntegerField(default=0, verbose_name="总 IP 数")
    used_ips = models.PositiveIntegerField(default=0, verbose_name="已使用")
    utilization = models.FloatField(default=0, verbose_name="使用率 (%)")
    recorded_at = models.DateTimeField(auto_now_add=True, verbose_name="记录时间")

    class Meta:
        verbose_name = "子网使用率"
        verbose_name_plural = verbose_name
        ordering = ("-recorded_at",)

    def __str__(self):
        return f"{self.subnet.network} @ {self.recorded_at:%Y-%m-%d %H:%M}"
