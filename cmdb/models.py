from annotated_types import T
from django.db import models
from django.db.models import JSONField
from logging import Logger
from .utils import config_parser

logger = Logger(__name__)

class Device(models.Model):
    hostname = models.CharField(max_length=100, unique=True, verbose_name='主机名')
    address = models.GenericIPAddressField(verbose_name='IP地址')
    username = models.CharField(max_length=50, verbose_name='用户名')
    password = models.CharField(max_length=100, verbose_name='密码')
    device_type = models.CharField(max_length=50, verbose_name='设备类型')
    connect_failed_at = models.DateTimeField(blank=True, null=True, verbose_name='连接失败时间')

    class Meta:
        verbose_name = '网络设备'
        verbose_name_plural = verbose_name
        
        indexes = [
		    models.Index(fields=['hostname'], name='idx_hostname'),
		    models.Index(fields=['address'], name='idx_address'),
        ]

    def __str__(self):
        return f"{self.hostname} ({self.address})"


class DeviceConfig(models.Model):
    """网络设备历史配置模型"""
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='configs', verbose_name='关联设备')
    config_text = models.TextField(verbose_name='配置内容')
    config_json = JSONField(blank=True, null=True, verbose_name='JSON格式的配置内容')
    latest = models.BooleanField(default=True)
    time = models.DateTimeField(auto_now_add=True, verbose_name='保存时间')

    def save(self, *args, **kwargs):
        """保存前解析文本配置, 并自动从config_json提取相关字段到各个配置模型"""
        if self.config_json == "null" or not self.config_json:
            self.config_json = config_parser.parse_config(self.config_text, self.device.device_type)
            logger.debug(f'解析结果为：{self.config_json}')
            self._extract()
        super().save(*args, **kwargs)


    def _save_interfaces(self, interfaces):
        interfaces_create = []
        for interface in interfaces:
            interfaces_create.append(Interface(
                config = self,
                interface = interface.get('interface'),
                description =  interface.get('description'),
                enabled =  interface.get('enabled'),
                vrf =  interface.get('vrf'),
                mode = interface.get('mode'),
                type = interface.get('type'),
                access_vlan = interface.get('access_vlan'),
                combo_type = interface.get('combo_type'),
                ip_address = interface.get('ip_address'),
                subnet_mask = interface.get('subnet_mask'),
            ))
        Interface.objects.bulk_create(interfaces_create, ignore_conflicts=False)


    def _extract(self):
            if self.config_json and 'interfaces' in self.config_json:
                self._save_interfaces(self.config_json['interfaces'])
            else:
                self.interface_json = None

            if self.config_json and 'virtuals' in self.config_json:
                self._save_virtual(self.config_json['virtuals'])
            else:
                self.virtual_json = None

            if self.config_json and 'pools' in self.config_json:
                self.pool_json = self.config_json['pools']
            else:
                self.pool_json = None

            if self.config_json and 'nodes' in self.config_json:
                self.node_json = self.config_json['nodes']
            else:
                self.node_json = None

    def _save_virtual(self, virtuals):
        virtuals_create = []
        for virtual in virtuals:
            if not virtual.get('profiles'):
                virtual['profiles'] = []
            elif isinstance(virtual['profiles'], dict):
                virtual['profiles'] = [virtual['profiles']['name']]
            elif isinstance(virtual['profiles'], list):
                virtual['profiles'] = [ _dict['name'] for _dict in virtual['profiles']]
            logger.info(f'profiles结果为: {virtual["profiles"]}')
            
            if not virtual.get('rules'):
                virtual['rules'] = []
            elif isinstance(virtual['rules'], dict):
                virtual['rules'] = [virtual['rules']['name']]
            elif isinstance(virtual['rules'], list):
                virtual['rules'] = [ _dict['name'] for _dict in virtual['rules']]
            logger.info(f'rules结果为: {virtual["rules"]}')
            virtuals_create.append(
                LtmVirtualServer(
                    config = self,
                    name = virtual.get('name'),
                    vs_address = virtual.get('vs_address'),
                    vs_port = virtual.get('vs_port'),
                    mask = virtual.get('mask'),
                    protocol = virtual.get('protocol'),
                    source = virtual.get('source'),
                    pool = virtual.get('pool'),
                    snat_type = virtual.get('snat_type'),
                    snat_pool = virtual.get('snat_pool'),
                    persist = virtual.get('persist', {}).get('name'),
                    profiles = virtual.get('profiles'),
                    rules = virtual.get('rules')
                )
            )
        LtmVirtualServer.objects.bulk_create(virtuals_create, ignore_conflicts=False)

    def _save_pools(self, pools):
        pools_create = []
        for pool in pools:
            pools_create.append(
                LtmPool(
                    config = self,
                    **pool
                )
            )
        LtmPool.objects.bulk_create(pools_create, ignore_conflicts=False)

    def _save_profiles(self, profiles):
        profiles_create = []
        for profile in profiles:
            profiles_create.append(
                LtmProfile(
                    config = self,
                    **profile
                )
            )
        LtmVirtualServer.objects.bulk_create(profiles_create, ignore_conflicts=False)

    class Meta:
        verbose_name = '设备配置'
        verbose_name_plural = verbose_name
        ordering = ['-time']  # 默认按时间倒序排序

        constraints = [
            models.UniqueConstraint(
                fields=['device'],
                condition=models.Q(latest=True),
                name='uni_latest_config_per_device'
            )
        ]

        indexes = [
		    models.Index(fields=['device', 'latest'], name='idx_config_latest'),
        ]

    def __str__(self):
        return f"{self.device.hostname} 配置 - {self.time.strftime('%Y-%m-%d %H:%M:%S')}" # type: ignore


class LtmVirtualServer(models.Model):
    config = models.ForeignKey(DeviceConfig, on_delete=models.CASCADE, related_name='virtual_servers')
    name = models.CharField(max_length=255)
    vs_address = models.CharField(max_length=255)
    vs_port = models.CharField(max_length=15, null=True)
    mask = models.CharField(max_length=15, null=True)
    protocol = models.CharField(max_length=15, null=True)
    source = models.CharField(max_length=15, null=True)
    snat_type = models.CharField(max_length=255, null=True)

    pool = models.CharField(max_length=255, null=True)
    snat_pool = models.CharField(max_length=255, null=True)
    persist = models.CharField(max_length=255, null=True)
    profiles = models.JSONField(default=list)
    rules = models.JSONField(default=list)

    class Meta:
        verbose_name = 'LTM Virtual'
        verbose_name_plural = verbose_name

        constraints = [
		    models.UniqueConstraint(
			    fields=['config', 'name'],
			    name='uni_vs_config'
		    )
        ]

        indexes = [
		    models.Index(fields=['name'], name='idx_vs_name'),
		    models.Index(fields=['pool'], name='idx_pool_name'),
		    models.Index(fields=['config'], name='idx_config'),
        ]


class LtmPool(models.Model):
    config = models.ForeignKey(DeviceConfig, models.CASCADE, related_name='pools')
    name = models.CharField(max_length=255)
    mode = models.CharField(max_length=255)

    monitors = models.JSONField(default=list)

    class Meta:
        verbose_name = 'LTM Pool'
        verbose_name_plural = verbose_name
        constraints = [
		    models.UniqueConstraint(
			    fields=['config', 'name'],
			    name='uni_pool_config'
		    )
        ]

        indexes = [
		    models.Index(fields=['config','name'], name='idx_pool_config'),
        ]


class LtmPoolMember(models.Model):
    pool = models.ForeignKey(LtmPool, models.CASCADE, related_name='members')
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    
    class Meta:
        verbose_name = 'LTM PoolMbr'
        verbose_name_plural = verbose_name

        indexes = [
		    models.Index(fields=['name'], name='idx_member_name'),
        ]


class LtmProfile(models.Model):
    config = models.ForeignKey(DeviceConfig, models.CASCADE, related_name='profiles')
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=255)
    raw = models.JSONField()

    class Meta:
        verbose_name = 'LTM Profile'
        verbose_name_plural = verbose_name

        indexes = [
		    models.Index(fields=['name'], name='idx_profile_name'),
        ]


class LtmIRule(models.Model):
    config = models.ForeignKey(DeviceConfig, models.CASCADE, related_name='irules')
    name = models.CharField(max_length=255)
    raw = models.JSONField()

    class Meta:
        verbose_name = 'LTM IRule'
        verbose_name_plural = verbose_name

        indexes = [
		    models.Index(fields=['name'], name='idx_rule_name'),
        ]


class LtmSNAT(models.Model):
    config = models.ForeignKey(DeviceConfig, models.CASCADE, related_name='snatpool')
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)

    class Meta:
        verbose_name = 'LTM SNAT'
        verbose_name_plural = verbose_name

        indexes = [
		    models.Index(fields=['name'], name='idx_snatpool_name'),
        ]


class LtmPersist(models.Model):
    config = models.ForeignKey(DeviceConfig, models.CASCADE, related_name='persist')
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=255)
    raw = models.JSONField()

    class Meta:
        verbose_name = 'LTM Persist'
        verbose_name_plural = verbose_name
        
        indexes = [
		    models.Index(fields=['name'], name='idx_persist_name'),
        ]


class GtmDatacenter(models.Model):
    config = models.ForeignKey(DeviceConfig, models.CASCADE, related_name='datacenters')
    name = models.CharField(max_length=255)


class GtmWideip(models.Model):
    config = models.ForeignKey(DeviceConfig, models.CASCADE, related_name='wideips')
    name = models.CharField(max_length=255)
    lb_mode = models.CharField(max_length=255)
    pools = models.JSONField(default=list, null=True)

    class Meta:
        verbose_name = 'GTM Wideip'
        verbose_name_plural = verbose_name

        constraints = [
		    models.UniqueConstraint(
			    fields=['config', 'name'],
			    name='uni_wideip_config'
		    )
        ]

        indexes = [
		    models.Index(fields=['name'], name='idx_wideip_name'),
		    models.Index(fields=['config'], name='idx_wideip_config'),
        ]


class GtmPool(models.Model):
    config = models.ForeignKey(DeviceConfig, models.CASCADE, related_name='gtmpools')
    name = models.CharField(max_length=255)
    lb_mode = models.CharField(max_length=255, default='round-robin')
    alternate_mode = models.CharField(max_length=255, default='round-robin')
    fallback_mode = models.CharField(max_length=255, default='return-to-dns')
    fallback_ip = models.GenericIPAddressField(null=True)
    ttl = models.IntegerField(default=30)
    members = models.JSONField(default=list)
    monitor = models.JSONField(default=list)


class Interface(models.Model):
    config = models.ForeignKey(DeviceConfig, models.CASCADE, related_name='interfaces')
    interface = models.CharField(max_length=255)
    description = models.CharField(max_length=255, null=True)
    enabled = models.BooleanField(default=False)
    vrf = models.CharField(max_length=255, null=True)
    mode = models.CharField(max_length=255, null=True)
    type = models.CharField(max_length=255, null=True)
    access_vlan = models.CharField(max_length=255, null=True)
    combo_type = models.CharField(max_length=255, null=True)
    ip_address = models.CharField(max_length=255, null=True)
    subnet_mask = models.CharField(max_length=255, null=True)
