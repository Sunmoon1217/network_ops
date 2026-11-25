"""软资产扩展表（T4）：域名与负载均衡服务。

一行 = 一个归并后的资产（FQDN / ``VIP#port``），公共属性在主表 ``ConfigurationItem``。
归并链路见 handbook/assets.md「软资产归并」。
"""

from django.db import models

from .ci import CIType, _CIExtension


class DomainAsset(_CIExtension):
    """域名资产：归一键是 FQDN（小写、去尾点）；``rtypes`` 记录出现过的记录类型。"""

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

    VIP 用 ``CharField`` 而非 ``GenericIPAddressField``：配置里的通配地址 / 非 IP 字面量
    不应在归并阶段失败。
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
