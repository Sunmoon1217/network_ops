"""云资源缓存表：阿里云 VPC / VSwitch / SLB 的本地副本（自原 ``apps/cloud`` 迁入）。

这些行是**外部事实的缓存**，不是人工维护的资产：随时可以整表重建，因此不挂任何源表外键，
也不参与软资产归并。它们与 ``ConfigurationItem`` 同处 assets，是为了将来能把云上资源
（VPC ⊃ VSwitch ⊃ ECS/SLB）与机房设备放进同一张资产图做关联查询。
同步动作在 ingest 的采集器，见 handbook/assets.md「云资源缓存」。
"""

from django.db import models


class AliyunVPC(models.Model):
    """阿里云 VPC"""

    vpc_id = models.CharField(max_length=64, unique=True, verbose_name="VPC ID")
    vpc_name = models.CharField(max_length=128, blank=True, null=True, verbose_name="名称")
    description = models.TextField(blank=True, null=True, verbose_name="描述")
    cidr_block = models.CharField(max_length=32, blank=True, null=True, verbose_name="IPv4 网段")
    ipv6_cidr_block = models.CharField(max_length=64, blank=True, null=True, verbose_name="IPv6 网段")
    owner_id = models.CharField(max_length=64, blank=True, null=True, verbose_name="Owner ID")
    region_id = models.CharField(max_length=32, blank=True, null=True, verbose_name="地域")
    resource_group_id = models.CharField(max_length=64, blank=True, null=True, verbose_name="资源组")
    vrouter_id = models.CharField(max_length=64, blank=True, null=True, verbose_name="路由表 ID")
    status = models.CharField(max_length=32, blank=True, null=True, verbose_name="状态")
    creation_time = models.DateTimeField(blank=True, null=True, verbose_name="创建时间")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    nat_gateway_ids = models.JSONField(blank=True, null=True, verbose_name="NAT 网关 ID")
    router_table_ids = models.JSONField(blank=True, null=True, verbose_name="路由表 ID 列表")
    secondary_cidr_blocks = models.JSONField(blank=True, null=True, verbose_name="附加网段")
    user_cidrs = models.JSONField(blank=True, null=True, verbose_name="用户网段")
    vswitch_ids = models.JSONField(blank=True, null=True, verbose_name="交换机 ID 列表")

    class Meta:
        verbose_name = "阿里云 VPC"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.vpc_name} ({self.vpc_id})"


class AliyunVSwitch(models.Model):
    """阿里云 VSwitch"""

    vswitch_id = models.CharField(max_length=64, unique=True, verbose_name="交换机 ID")
    vswitch_name = models.CharField(max_length=128, blank=True, null=True, verbose_name="名称")
    description = models.TextField(blank=True, null=True, verbose_name="描述")
    vpc_id = models.CharField(max_length=64, blank=True, null=True, verbose_name="所属 VPC")
    cidr_block = models.CharField(max_length=32, blank=True, null=True, verbose_name="IPv4 网段")
    ipv6_cidr_block = models.CharField(max_length=64, blank=True, null=True, verbose_name="IPv6 网段")
    zone_id = models.CharField(max_length=32, blank=True, null=True, verbose_name="可用区")
    available_ip_address_count = models.IntegerField(blank=True, null=True, verbose_name="可用 IP 数")
    status = models.CharField(max_length=32, blank=True, null=True, verbose_name="状态")
    creation_time = models.DateTimeField(blank=True, null=True, verbose_name="创建时间")
    resource_group_id = models.CharField(max_length=64, blank=True, null=True, verbose_name="资源组")
    network_acl_id = models.CharField(max_length=64, blank=True, null=True, verbose_name="网络 ACL")

    route_table = models.JSONField(blank=True, null=True, verbose_name="路由表")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "阿里云交换机"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.vswitch_name} ({self.vswitch_id})"


class AliyunLoadBalancer(models.Model):
    """阿里云负载均衡"""

    load_balancer_id = models.CharField(max_length=64, unique=True, verbose_name="实例 ID")
    load_balancer_name = models.CharField(max_length=128, blank=True, null=True, verbose_name="名称")
    load_balancer_status = models.CharField(max_length=32, blank=True, null=True, verbose_name="实例状态")
    business_status = models.CharField(max_length=32, blank=True, null=True, verbose_name="业务状态")
    spec_type = models.CharField(max_length=32, blank=True, null=True, verbose_name="规格")
    address_type = models.CharField(max_length=32, blank=True, null=True, verbose_name="地址类型")
    region_id = models.CharField(max_length=32, blank=True, null=True, verbose_name="地域")
    vpc_id = models.CharField(max_length=64, blank=True, null=True, verbose_name="所属 VPC")
    vswitch_id = models.CharField(max_length=64, blank=True, null=True, verbose_name="所属交换机")
    network_type = models.CharField(max_length=32, blank=True, null=True, verbose_name="网络类型")
    address = models.GenericIPAddressField(blank=True, null=True, verbose_name="服务地址")
    address_ip_version = models.CharField(max_length=32, blank=True, null=True, verbose_name="IP 版本")
    internet_charge_type = models.CharField(max_length=32, blank=True, null=True, verbose_name="计费方式")
    bandwidth = models.IntegerField(blank=True, null=True, verbose_name="带宽")
    resource_group_id = models.CharField(max_length=64, blank=True, null=True, verbose_name="资源组")
    createtime = models.DateTimeField(blank=True, null=True, verbose_name="创建时间")
    backend_servers = models.JSONField(blank=True, null=True, verbose_name="后端服务器")
    listener_ports = models.JSONField(blank=True, null=True, verbose_name="监听端口")
    listener_ports_and_protocol = models.JSONField(blank=True, null=True, verbose_name="监听端口与协议")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "阿里云负载均衡"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.load_balancer_name} ({self.load_balancer_id})"
