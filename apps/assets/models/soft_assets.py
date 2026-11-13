"""软资产扩展表（T4）：域名与负载均衡服务。

``GtmWideip`` / ``LtmVirtualServer`` 是**某台设备上的一条配置行**（一设备一行、跨设备重复），
不是资产；归并链路按归一键跨设备去重后落这里，一行 = 一个 FQDN / 一个 ``VIP#port``，
设备退居「部署位置」多值。配置行保持权威、不动不删，只在详情 / 展开时作为证据反查。

公共属性（``ci_id`` / ``ci_type`` / ``name`` / ``tags`` / ``monitor_status``）在主表
``ConfigurationItem``；本模块只放归并产出的专属字段。
"""

from django.db import models

from .ci import CIType, _CIExtension


class DomainAsset(_CIExtension):
    """域名资产：归一键是 FQDN（小写、去尾点）。

    一个 FQDN 一行，``rtypes`` 记录该域名出现过哪些记录类型（A / AAAA / CNAME），
    不按 ``(域名, rtype)`` 拆行——记录类型是属性的多值，不是不同的资产。
    """

    EXPECTED_CI_TYPE = CIType.DOMAIN

    fqdn = models.CharField(max_length=255, unique=True, verbose_name="域名")
    rtypes = models.JSONField(default=list, blank=True, verbose_name="记录类型")
    ttl = models.IntegerField(null=True, blank=True, verbose_name="TTL")
    lb_mode = models.CharField(max_length=100, blank=True, default="", verbose_name="负载算法")
    pools = models.JSONField(default=list, blank=True, verbose_name="关联池")
    fallback_ips = models.JSONField(default=list, blank=True, verbose_name="回退 IP")
    vips = models.JSONField(default=list, blank=True, verbose_name="关联 VIP")
    devices = models.JSONField(default=list, blank=True, verbose_name="部署设备")
    inconsistent = models.BooleanField(default=False, verbose_name="配置不一致")
    conflict_fields = models.JSONField(default=list, blank=True, verbose_name="冲突字段")

    class Meta:
        verbose_name = "域名资产"
        verbose_name_plural = verbose_name
        ordering = ("fqdn",)

    def __str__(self):
        return self.fqdn


class LoadBalancerService(_CIExtension):
    """负载均衡服务资产：归一键是 ``VIP#port``（IPv6 也用 ``#`` 分隔）。

    ``asset_key`` 冗余保存拼接结果，用于唯一约束与 ``?search=`` 直查；
    ``vip`` / ``port`` 分开存便于按地址或端口过滤。VIP 用 ``CharField`` 而非
    ``GenericIPAddressField``：配置里可能出现的通配地址 / 非 IP 字面量不应在归并阶段失败。
    """

    EXPECTED_CI_TYPE = CIType.LOAD_BALANCER_SERVICE

    asset_key = models.CharField(max_length=320, unique=True, verbose_name="归一键")
    vip = models.CharField(max_length=255, verbose_name="VIP")
    port = models.CharField(max_length=15, blank=True, default="", verbose_name="端口")
    protocol = models.CharField(max_length=15, blank=True, default="", verbose_name="协议")
    pools = models.JSONField(default=list, blank=True, verbose_name="关联池")
    member_count = models.PositiveIntegerField(default=0, verbose_name="成员数")
    profiles = models.JSONField(default=list, blank=True, verbose_name="Profile 列表")
    rules = models.JSONField(default=list, blank=True, verbose_name="iRule 列表")
    devices = models.JSONField(default=list, blank=True, verbose_name="部署设备")
    status = models.CharField(max_length=20, blank=True, default="", verbose_name="状态")
    inconsistent = models.BooleanField(default=False, verbose_name="配置不一致")
    conflict_fields = models.JSONField(default=list, blank=True, verbose_name="冲突字段")

    class Meta:
        verbose_name = "负载均衡服务资产"
        verbose_name_plural = verbose_name
        ordering = ("vip", "port")

    def __str__(self):
        return self.asset_key
