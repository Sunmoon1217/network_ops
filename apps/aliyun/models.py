from django.db import models

# 阿里云资源模型（待后续添加：账户、资源同步记录、VSW/SLB/SLS/ECS 缓存等)


class AliyunVPC(models.Model):
    """阿里云 VPC"""

    vpc_id = models.CharField(max_length=64, unique=True)
    vpc_name = models.CharField(max_length=128, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    cidr_block = models.CharField(max_length=32, blank=True, null=True)
    ipv6_cidr_block = models.CharField(max_length=64, blank=True, null=True)
    owner_id = models.CharField(max_length=64, blank=True, null=True)
    region_id = models.CharField(max_length=32, blank=True, null=True)
    resource_group_id = models.CharField(max_length=64, blank=True, null=True)
    vrouter_id = models.CharField(max_length=64, blank=True, null=True)
    status = models.CharField(max_length=32, blank=True, null=True)
    creation_time = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    nat_gateway_ids = models.JSONField(blank=True, null=True)
    router_table_ids = models.JSONField(blank=True, null=True)
    secondary_cidr_blocks = models.JSONField(blank=True, null=True)
    user_cidrs = models.JSONField(blank=True, null=True)
    vswitch_ids = models.JSONField(blank=True, null=True)

    def __str__(self):
        return f"{self.vpc_name} ({self.vpc_id})"


class AliyunVSwitch(models.Model):
    """阿里云 VSwitch"""

    vswitch_id = models.CharField(max_length=64, unique=True)
    vswitch_name = models.CharField(max_length=128, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    vpc_id = models.CharField(max_length=64, blank=True, null=True)
    cidr_block = models.CharField(max_length=32, blank=True, null=True)
    ipv6_cidr_block = models.CharField(max_length=64, blank=True, null=True)
    zone_id = models.CharField(max_length=32, blank=True, null=True)
    available_ip_address_count = models.IntegerField(blank=True, null=True)
    status = models.CharField(max_length=32, blank=True, null=True)
    creation_time = models.DateTimeField(blank=True, null=True)
    resource_group_id = models.CharField(max_length=64, blank=True, null=True)
    network_acl_id = models.CharField(max_length=64, blank=True, null=True)

    route_table = models.JSONField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.vswitch_name} ({self.vswitch_id})"


class AliyunLoadBalancer(models.Model):
    """阿里云负载均衡"""

    load_balancer_id = models.CharField(max_length=64, unique=True)
    load_balancer_name = models.CharField(max_length=128, blank=True, null=True)
    load_balancer_status = models.CharField(max_length=32, blank=True, null=True)
    business_status = models.CharField(max_length=32, blank=True, null=True)
    spec_type = models.CharField(max_length=32, blank=True, null=True)
    address_type = models.CharField(max_length=32, blank=True, null=True)
    region_id = models.CharField(max_length=32, blank=True, null=True)
    vpc_id = models.CharField(max_length=64, blank=True, null=True)
    vswitch_id = models.CharField(max_length=64, blank=True, null=True)
    network_type = models.CharField(max_length=32, blank=True, null=True)
    address = models.GenericIPAddressField(blank=True, null=True)
    address_ip_version = models.CharField(max_length=32, blank=True, null=True)
    internet_charge_type = models.CharField(max_length=32, blank=True, null=True)
    bandwidth = models.IntegerField(blank=True, null=True)
    resource_group_id = models.CharField(max_length=64, blank=True, null=True)
    createtime = models.DateTimeField(blank=True, null=True)
    backend_servers = models.JSONField(blank=True, null=True)
    listener_ports = models.JSONField(blank=True, null=True)
    listener_ports_and_protocol = models.JSONField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.load_balancer_name} ({self.load_balancer_id})"


class AliyunSLBHealthCheck(models.Model):
    """阿里云负载均衡健康检查"""

    ...


class AliyunSLBListener(models.Model):
    """阿里云负载均衡监听器"""

    ...


class AliyunSLBVServerGroup(models.Model):
    """阿里云负载均衡虚拟服务器组"""

    ...


class AliyunSLBMSServer(models.Model):
    """阿里云负载均衡主备服务群组"""

    ...


class AliyunSLBRule(models.Model):
    """阿里云负载均衡转发规则"""

    ...
