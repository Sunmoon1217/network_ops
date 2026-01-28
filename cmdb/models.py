from django.db import models
from django.db.models import JSONField

class Device(models.Model):
    hostname = models.CharField(max_length=100, unique=True, verbose_name='主机名')
    address = models.GenericIPAddressField(verbose_name='IP地址')
    username = models.CharField(max_length=50, verbose_name='用户名')
    password = models.CharField(max_length=100, verbose_name='密码')
    device_type = models.CharField(max_length=50, verbose_name='设备类型')
    connect_failed_at = models.DateTimeField(blank=True, null=True, verbose_name='连接失败时间')

    class Meta:
        verbose_name = '网络设备'
        verbose_name_plural = '网络设备'

    def __str__(self):
        return f"{self.hostname} ({self.address})"

class DeviceConfig(models.Model):
    """网络设备历史配置模型"""
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='configs', verbose_name='关联设备')
    config_text = models.TextField(verbose_name='配置内容')
    config_json = JSONField(blank=True, null=True, verbose_name='JSON格式的配置内容')
    interface_json = JSONField(blank=True, null=True, verbose_name='JSON格式的接口配置内容')  # 新增字段
    time = models.DateTimeField(auto_now_add=True, verbose_name='保存时间')

    def save(self, *args, **kwargs):
        """保存前自动从config_json提取interfaces字段到interface_json"""
        if self.config_json and 'interfaces' in self.config_json:
            self.interface_json = self.config_json['interfaces']
        else:
            self.interface_json = None
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = '设备配置'
        verbose_name_plural = '设备配置'
        ordering = ['-time']  # 默认按时间倒序排序

    def __str__(self):
        return f"{self.device.hostname} 配置 - {self.time.strftime('%Y-%m-%d %H:%M:%S')}" # type: ignore
