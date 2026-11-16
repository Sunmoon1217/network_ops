"""网络域历史资产模型（原单文件 ``assets/models.py`` 的内容）。

T1 拆分时把这段原样搬进来，一字未改：模型之间 35 处跨类直接引用
（``ForeignKey(DataCenter, ...)`` 等）都还在同一个模块里，不会有循环 import。
将来若按域细分，从这里分出去即可；``__init__.py`` 只做 re-export。
"""

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
    datacenter = models.ForeignKey(DataCenter, on_delete=models.CASCADE, related_name="rooms", verbose_name="所属数据中心")
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
    power_capacity = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="额定功率(kW)")
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
        ordering = ("name",)

    def __str__(self):
        return self.name


class DeviceModel(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="设备型号")
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="device_models", verbose_name="所属厂商")

    class Meta:
        verbose_name = "设备型号"
        verbose_name_plural = verbose_name
        ordering = ("name",)

    def __str__(self):
        return f"{self.vendor.name} {self.name}"


class Device(models.Model):
    DEVICE_TYPE_CHOICES = (
        ("firewall", "防火墙"),
        ("switch", "交换机"),
        ("slb", "服务器负载均衡"),
        ("gslb", "全局负载均衡"),
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
        ordering = ("hostname",)

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
        verbose_name="关联设备",
    )
    address = models.GenericIPAddressField(blank=True, null=True, verbose_name="连接地址")
    connection_type = models.CharField(max_length=20, choices=CONNECTION_TYPE_CHOICES, default="napalm", verbose_name="连接类型")
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
        constraints = (models.UniqueConstraint(fields=["device", "account_type"], name="uni_deviceconn_device_account"),)
        ordering = ("-created_at", "-pk")

    def __str__(self):
        return f"{self.device.hostname} ({self.connection_type})"

    def get_address(self) -> str:
        """获取连接地址（优先级：连接地址 > 设备地址）"""
        if self.address:
            return self.address
        if self.device:
            return self.device.hostname
        return ""


class DeviceGroup(models.Model):
    """设备组。

    组类型属于组本身，成员只表达「该设备在这个组里扮演什么角色」。
    堆叠（stack）组内多台物理设备共用一个配置文件，备机的配置归属主设备。
    """

    GROUP_TYPE_CHOICES = (
        ("cluster", "集群"),
        ("ha", "主备"),
        ("failover", "故障接管"),
        ("stack", "堆叠"),
        ("single", "单机"),
    )

    name = models.CharField(max_length=100, unique=True, verbose_name="设备组名称")
    group_type = models.CharField(max_length=20, choices=GROUP_TYPE_CHOICES, default="single", verbose_name="组类型")
    description = models.CharField(max_length=255, blank=True, default="", verbose_name="描述")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    if TYPE_CHECKING:
        members: QuerySet["DeviceGroupMember"]

        def get_group_type_display(self) -> str: ...

    class Meta:
        verbose_name = "设备组"
        verbose_name_plural = verbose_name
        ordering = ("name",)

    def __str__(self):
        return f"{self.name} ({self.get_group_type_display()})"

    if TYPE_CHECKING:
        device_id: int


class DeviceGroupMember(models.Model):
    """设备组成员。

    同一设备可加入多个组（不同组表达不同维度的关系，如既在堆叠组又在主备组），
    因此不对设备做唯一限制。
    """

    ROLE_CHOICES = (
        ("master", "主"),
        ("backup", "备"),
        ("member", "成员"),
    )

    group = models.ForeignKey(DeviceGroup, on_delete=models.CASCADE, related_name="members", verbose_name="设备组")
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="group_memberships", verbose_name="设备")
    device_role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="member", verbose_name="设备角色")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "设备组成员"
        verbose_name_plural = verbose_name
        constraints = (models.UniqueConstraint(fields=["group", "device"], name="uni_group_member"),)
        ordering = ("group", "device", "-pk")

    def __str__(self):
        return f"{self.group.name} / {self.device.hostname} ({self.device_role})"

    if TYPE_CHECKING:
        device_id: int


# SLB (LTM - Local Traffic Manager)


# GSLB (GTM - Global Traffic Manager)


# Firewall Policy


# IPAM


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

    # IPv6 CIDR 全展开最长 43 字符（ffff:...:ffff/128），18 只够 IPv4，故取 45
    network = models.CharField(max_length=45, unique=True, verbose_name="网段 (CIDR)")
    tags = models.ManyToManyField(Tag, blank=True, related_name="subnets", verbose_name="标签")
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="children", verbose_name="父网段")
    gateway = models.GenericIPAddressField(null=True, blank=True, verbose_name="默认网关")
    vlan = models.CharField(max_length=20, blank=True, default="", verbose_name="VLAN")
    datacenter = models.ForeignKey(DataCenter, on_delete=models.SET_NULL, null=True, blank=True, related_name="subnets", verbose_name="数据中心")
    security_zone = models.ForeignKey(SecurityZone, on_delete=models.SET_NULL, null=True, blank=True, related_name="subnets", verbose_name="安全区")
    vrf = models.CharField(max_length=50, blank=True, default="", verbose_name="所属VRF")
    description = models.CharField(max_length=255, blank=True, default="", verbose_name="描述")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    if TYPE_CHECKING:
        children: QuerySet["Subnet"]
        ip_addresses: QuerySet["IPAddress"]

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
    subnet = models.ForeignKey(Subnet, on_delete=models.SET_NULL, null=True, blank=True, related_name="ip_addresses", verbose_name="所属网段")
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
    device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True, related_name="ip_addresses", verbose_name="关联设备")
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


# 网络拓扑


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


# ARP/MAC 表


# 子网使用率趋势


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


# 服务器负责人（人工维护）


class ServerOwner(models.Model):
    """服务器 IP 与负责人的对应关系。

    人工维护、不从设备配置提取，所以是裸 ``models.Model``（不进 ``ConfigBase``）。
    ``ip`` 是查询键：资产分析拿到链路最后的 IP 后按它反查负责人；用
    ``GenericIPAddressField`` 是为了让 IPv6 统一小写压缩，避免 ``2001:DB8::1``
    与 ``2001:db8::1`` 匹配不上。
    """

    STATUS_CHOICES = (("enabled", "启用"), ("disabled", "停用"))

    hostname = models.CharField(max_length=255, blank=True, default="", verbose_name="主机名")
    ip = models.GenericIPAddressField(unique=True, verbose_name="IP 地址")
    owner = models.CharField(max_length=255, blank=True, default="", verbose_name="负责人")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="enabled", verbose_name="状态")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "服务器负责人"
        verbose_name_plural = verbose_name
        ordering = ("ip",)

    def __str__(self):
        return f"{self.ip} - {self.owner}" if self.owner else self.ip
