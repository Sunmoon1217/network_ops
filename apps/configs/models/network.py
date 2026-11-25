"""配置行模型：``ConfigBase`` 的 25 个子类（设备上的一条配置行）。

模型间直接用类名引用（同在本模块）；``DeviceConfig`` 是配置快照、不继承 ConfigBase。
分类判据见 handbook/assets.md「资产分类边界」。
"""

from typing import TYPE_CHECKING

from django.db import models
from django.db.models import QuerySet

from configs.models.base import ConfigBase


class Vlan(ConfigBase):
    """VLAN"""

    vid = models.PositiveIntegerField(verbose_name="VLAN ID")
    name = models.CharField(max_length=100, blank=True, default="", verbose_name="VLAN名称")
    description = models.CharField(max_length=255, blank=True, default="", verbose_name="描述")

    class Meta:
        verbose_name = "VLAN"
        verbose_name_plural = verbose_name
        ordering = ("vid",)
        constraints = (models.UniqueConstraint(fields=["device", "vid"], name="uni_vlan_device_vid"),)

    def __str__(self):
        return f"{self.device.hostname} - VLAN {self.vid}" + (f" ({self.name})" if self.name else "")


class Vrf(ConfigBase):
    """VRF"""

    name = models.CharField(max_length=255, verbose_name="名称")
    rd = models.CharField(max_length=50, blank=True, default="", verbose_name="RD")
    description = models.TextField(blank=True, default="", verbose_name="描述")

    class Meta:
        verbose_name = "VRF"
        verbose_name_plural = verbose_name
        constraints = (models.UniqueConstraint(fields=["device", "name"], name="uni_vrf_device_name"),)
        ordering = ("device", "name")

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
    vrf = models.ForeignKey(Vrf, on_delete=models.SET_NULL, null=True, blank=True, related_name="interfaces", verbose_name="VRF")
    type = models.CharField(max_length=255, null=True, verbose_name="接口类型")
    combo_type = models.CharField(max_length=255, null=True, verbose_name="Combo类型")
    ip_address = models.CharField(max_length=255, null=True, verbose_name="IP地址")
    subnet_mask = models.CharField(max_length=255, null=True, verbose_name="子网掩码")

    class Meta:
        verbose_name = "网络接口"
        verbose_name_plural = verbose_name
        constraints = (models.UniqueConstraint(fields=["device", "interface"], name="uni_device_interface"),)
        ordering = ("device", "interface")

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
        constraints = (models.UniqueConstraint(fields=["device", "username"], name="uni_deviceaccount_device_username"),)
        ordering = ("device", "username", "-pk")

    def __str__(self):
        return f"{self.device.hostname} / {self.username}"


class SnmpConfig(ConfigBase):
    """SNMP配置基线"""

    version = models.CharField(max_length=10, choices=[("v1", "v1"), ("v2c", "v2c"), ("v3", "v3")], default="v2c", verbose_name="SNMP版本")
    community_read = models.CharField(max_length=100, blank=True, default="", verbose_name="读社区字符串")
    community_write = models.CharField(max_length=100, blank=True, default="", verbose_name="写社区字符串")
    port = models.PositiveIntegerField(default=161, verbose_name="监听端口")
    trap_enabled = models.BooleanField(default=False, verbose_name="启用Trap")
    trap_server = models.GenericIPAddressField(blank=True, null=True, verbose_name="Trap服务器")
    trap_port = models.PositiveIntegerField(default=162, verbose_name="Trap端口")
    enabled = models.BooleanField(default=True, verbose_name="启用SNMP")

    class Meta:
        verbose_name = "SNMP配置"
        verbose_name_plural = verbose_name
        ordering = ("-created_at", "-pk")

    def __str__(self):
        return f"{self.device.hostname} SNMP"


class NtpConfig(ConfigBase):
    """NTP配置基线"""

    server1 = models.GenericIPAddressField(verbose_name="NTP服务器1")
    server2 = models.GenericIPAddressField(blank=True, null=True, verbose_name="NTP服务器2")
    server3 = models.GenericIPAddressField(blank=True, null=True, verbose_name="NTP服务器3")
    timezone = models.CharField(max_length=50, default="UTC", verbose_name="时区")
    sync_interval = models.PositiveIntegerField(default=64, verbose_name="同步间隔(秒)")
    enabled = models.BooleanField(default=True, verbose_name="启用NTP")

    class Meta:
        verbose_name = "NTP配置"
        verbose_name_plural = verbose_name
        ordering = ("-created_at", "-pk")

    def __str__(self):
        return f"{self.device.hostname} NTP"


class SyslogConfig(ConfigBase):
    """Syslog配置基线"""

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

    class Meta:
        verbose_name = "Syslog配置"
        verbose_name_plural = verbose_name
        ordering = ("-created_at", "-pk")

    def __str__(self):
        return f"{self.device.hostname} Syslog"


class LtmVirtualServer(ConfigBase):
    """虚拟服务器"""

    name = models.CharField(max_length=255, verbose_name="名称")
    vs_address = models.CharField(max_length=255, verbose_name="虚拟地址")
    vs_port = models.CharField(max_length=15, null=True, verbose_name="端口")
    mask = models.CharField(max_length=15, null=True, verbose_name="掩码")
    protocol = models.CharField(max_length=15, null=True, verbose_name="协议")
    status = models.CharField(max_length=20, default="enabled", verbose_name="状态")
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
        ordering = ("device", "name")

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
        ordering = ("device", "name")


class LtmPoolMember(ConfigBase):
    """LTM 池成员

    ``pool_name`` 是池名称而不是外键，归属靠 ``device`` 限定：``LtmPool`` 的
    ``(device, name)`` 唯一，所以「设备 + 池名」才能定位到唯一的池；去掉 ``device``
    会让不同设备的同名池成员互相串（分析 / 路径追踪按名字全局匹配，删池会跨设备误删）。
    """

    pool_name = models.CharField(max_length=255, blank=True, default="", verbose_name="关联池名称")
    name = models.CharField(max_length=255, verbose_name="成员名称")
    address = models.CharField(max_length=255, verbose_name="地址")
    port = models.CharField(max_length=15, blank=True, default="", verbose_name="端口")

    class Meta:
        verbose_name = "LTM Pool Member"
        verbose_name_plural = verbose_name
        ordering = ("device", "pool_name", "name", "-pk")
        # 唯一性必须带上 port：F5 同一节点可以在多个端口上做成员，剥掉
        # /Common/node_a:80 的端口后 name 都是 node_a，只约束 name 会误杀
        constraints = (models.UniqueConstraint(fields=["device", "pool_name", "name", "port"], name="uni_pool_member_device_pool_node_port"),)


class LtmProfile(ConfigBase):
    """LTM Profile"""

    name = models.CharField(max_length=255, verbose_name="名称")
    type = models.CharField(max_length=255, verbose_name="类型")
    raw = models.JSONField(verbose_name="原始配置")

    class Meta:
        verbose_name = "LTM Profile"
        verbose_name_plural = verbose_name
        ordering = ("device", "name", "-pk")


class LtmIRule(ConfigBase):
    """LTM iRule"""

    name = models.CharField(max_length=255, verbose_name="名称")
    raw = models.JSONField(verbose_name="原始配置")

    class Meta:
        verbose_name = "LTM iRule"
        verbose_name_plural = verbose_name
        ordering = ("device", "name", "-pk")


class LtmSNAT(ConfigBase):
    """LTM SNAT"""

    name = models.CharField(max_length=255, verbose_name="名称")
    address = models.CharField(max_length=255, verbose_name="地址")

    class Meta:
        verbose_name = "LTM SNAT"
        verbose_name_plural = verbose_name
        ordering = ("device", "name", "-pk")


class LtmPersist(ConfigBase):
    """LTM 会话保持"""

    name = models.CharField(max_length=255, verbose_name="名称")
    type = models.CharField(max_length=255, verbose_name="类型")
    raw = models.JSONField(verbose_name="原始配置")

    class Meta:
        verbose_name = "LTM Persist"
        verbose_name_plural = verbose_name
        ordering = ("device", "name", "-pk")


class GtmDatacenter(ConfigBase):
    """GTM 数据中心"""

    name = models.CharField(max_length=255, verbose_name="名称")

    class Meta:
        verbose_name = "GTM Datacenter"
        verbose_name_plural = verbose_name
        ordering = ("device", "name", "-pk")


class GtmWideip(ConfigBase):
    """GTM Wide IP"""

    name = models.CharField(max_length=255, verbose_name="域名")
    rtype = models.CharField(max_length=255, verbose_name="记录类型")
    lb_mode = models.CharField(max_length=255, verbose_name="负载模式")
    pools = models.JSONField(default=list, null=True, verbose_name="关联池列表")

    def pool_entries(self) -> list[dict]:
        """`pools` 的两种历史形态统一成 `[{"name", "order", "ratio"}, ...]`。

        旧数据是纯池名列表 ``["pool_web"]``（Saver 曾把权重丢掉）；2026-09 起
        `f5_gtm.ttp` wideip 组里每个池的 ``pool_order`` / ``pool_ratio`` 会一起存进来：
        ``[{"name": "pool_web", "order": 5, "ratio": 3}]``。

        读侧一律走这里——老数据不丢，新数据带权重，别再直接遍历 `pools`。
        """
        entries = []
        for item in self.pools or []:
            if isinstance(item, dict):
                name = item.get("name") or item.get("pool_name") or ""
                order, ratio = item.get("order"), item.get("ratio")
            else:
                name, order, ratio = str(item or ""), None, None
            if name:
                entries.append({"name": name, "order": order, "ratio": ratio})
        return entries

    @property
    def pool_names(self) -> list[str]:
        """只要池名：查询反查、计数、逐池循环都用它。"""
        return [entry["name"] for entry in self.pool_entries()]

    class Meta:
        verbose_name = "GTM Wide IP"
        verbose_name_plural = verbose_name
        constraints = (models.UniqueConstraint(fields=["device", "name", "rtype"], name="uni_rtype_wideip_device"),)
        ordering = ("device", "name")


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
        ordering = ("device", "name", "-pk")


class GtmServer(ConfigBase):
    """GTM 服务器：gtm server，承载若干 virtual server"""

    name = models.CharField(max_length=255, verbose_name="服务器名称")
    datacenter = models.CharField(max_length=255, blank=True, default="", verbose_name="数据中心")
    monitor = models.CharField(max_length=255, blank=True, default="", verbose_name="监控")
    server_type = models.CharField(max_length=255, blank=True, default="", verbose_name="产品类型")

    class Meta:
        verbose_name = "GTM Server"
        verbose_name_plural = verbose_name
        constraints = (models.UniqueConstraint(fields=["device", "name"], name="uni_gtmserver_device_name"),)
        ordering = ("device", "name", "-pk")


class GtmVServer(ConfigBase):
    """GTM 虚拟服务器：gtm server 下的 virtual-servers，记录地址与端口"""

    server = models.ForeignKey(GtmServer, on_delete=models.CASCADE, related_name="virtual_servers", verbose_name="所属服务器")
    name = models.CharField(max_length=255, verbose_name="虚拟服务器名称")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="地址")
    port = models.CharField(max_length=15, blank=True, default="", verbose_name="端口")
    monitor = models.CharField(max_length=255, blank=True, default="", verbose_name="监控")

    if TYPE_CHECKING:
        server_id: int

    class Meta:
        verbose_name = "GTM Virtual Server"
        verbose_name_plural = verbose_name
        constraints = (models.UniqueConstraint(fields=["device", "server", "name"], name="uni_gtmvserver_device_server_name"),)
        ordering = ("device", "server", "name", "-pk")


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
    parent = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="children", verbose_name="上级地址簿")
    description = models.TextField(blank=True, default="", verbose_name="描述")

    if TYPE_CHECKING:
        children: QuerySet["AddressBook"]

    class Meta:
        verbose_name = "地址簿"
        verbose_name_plural = verbose_name
        ordering = ("device", "name", "-pk")


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
        # 行级自然键唯一：一个服务名允许多行端口定义（tcp 22 与 udp 53 各一行），
        # ServiceSaver 按这组键做差量。为什么不再按 (device, name) 唯一见 handbook/assets.md
        constraints = (
            models.UniqueConstraint(
                fields=["device", "name", "protocol", "port", "port2"],
                name="uni_service_natural_key",
            ),
        )
        ordering = ("name",)


class Policy(ConfigBase):
    """安全策略"""

    ACTION_CHOICES = (("allow", "允许"), ("deny", "拒绝"))
    policy_id = models.CharField(max_length=50, verbose_name="策略ID")
    order = models.PositiveIntegerField(verbose_name="策略顺序")
    name = models.CharField(max_length=255, verbose_name="策略名称")
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, default="allow", verbose_name="动作")
    enabled = models.BooleanField(default=True, verbose_name="启用")
    source_addresses = models.ManyToManyField(AddressBook, related_name="source_policies", verbose_name="源地址")
    destination_addresses = models.ManyToManyField(AddressBook, related_name="destination_policies", verbose_name="目的地址")
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
        ordering = ("device", "order")


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
    # 三个匹配维度都允许为空：不同厂商的 NAT 配置能提供的信息差别很大
    # （cisco 的 nat group 只有 host/public_ip，完全给不出 service）
    source_addresses = models.ManyToManyField(AddressBook, blank=True, related_name="source_nat_rules", verbose_name="匹配源地址")
    destination_addresses = models.ManyToManyField(AddressBook, blank=True, related_name="destination_nat_rules", verbose_name="匹配目的地址")
    services = models.ManyToManyField(Service, blank=True, related_name="nat_rules", verbose_name="匹配服务")
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
        ordering = ("device", "order")


class Route(ConfigBase):
    """路由

    ``vrf`` 与继承来的 ``device`` 是冗余的——``Route`` 通过 ``vrf`` 表达归属，
    ``device`` 便于直接按设备查询。Saver 入库时会用 ``vrf.device`` 保持两者一致。
    """

    PROTOCOL_CHOICES = (
        ("static", "静态"),
        ("connected", "直连"),
        ("ospf", "OSPF"),
        ("bgp", "BGP"),
        ("rip", "RIP"),
        ("other", "其他"),
    )

    vrf = models.ForeignKey(Vrf, on_delete=models.CASCADE, related_name="routes", verbose_name="VRF")
    # 同 Subnet.network：IPv6 CIDR 全展开最长 43 字符，18 不够
    destination = models.CharField(max_length=45, verbose_name="目的网段 (CIDR)")
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
        ordering = ("vrf", "destination", "nexthop", "-pk")

    def __str__(self):
        return f"{self.destination} → {self.nexthop or self.interface}"


class ArpMac(ConfigBase):
    """ARP/MAC 地址表（2026-11-16 改继承 ConfigBase，随配置行家族迁入 configs）"""

    ARP_TYPE_CHOICES = (
        ("dynamic", "动态"),
        ("static", "静态"),
    )
    STATUS_CHOICES = (
        ("normal", "正常"),
        ("aging", "老化中"),
        ("conflict", "冲突"),
    )

    vlan = models.CharField(max_length=50, blank=True, default="", verbose_name="VLAN")
    interface = models.CharField(max_length=255, blank=True, default="", verbose_name="接口")
    ip_address = models.GenericIPAddressField(verbose_name="IP 地址")
    mac_address = models.CharField(max_length=17, verbose_name="MAC 地址")
    vendor = models.CharField(max_length=100, blank=True, default="", verbose_name="厂商")
    arp_type = models.CharField(max_length=20, choices=ARP_TYPE_CHOICES, default="dynamic", verbose_name="ARP 类型")
    learned_at = models.DateTimeField(null=True, blank=True, verbose_name="学习时间")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="normal", verbose_name="状态")

    class Meta:
        verbose_name = "ARP/MAC"
        verbose_name_plural = verbose_name
        ordering = ("-updated_at",)
        constraints = (models.UniqueConstraint(fields=["device", "ip_address", "mac_address"], name="uni_arpmac_device_ip_mac"),)

    def __str__(self):
        return f"{self.ip_address} → {self.mac_address}"
