import secrets

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """扩展用户模型"""

    phone = models.CharField(max_length=20, blank=True, default="", verbose_name="手机号")
    avatar = models.CharField(max_length=255, blank=True, default="", verbose_name="头像URL")

    class Meta:
        verbose_name = "用户"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.username


class Token(models.Model):
    """API Token"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tokens",
        verbose_name="用户",
    )
    key = models.CharField(max_length=64, unique=True, verbose_name="Token Key")
    created = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "Token"
        verbose_name_plural = verbose_name

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = secrets.token_hex(32)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.key[:8]}..."


class Task(models.Model):
    """任务主记录"""

    TASK_TYPES = (
        ("collect_config", "采集配置"),
        ("backup_config", "备份配置"),
        ("ansible_playbook", "Ansible执行"),
        ("batch_collect", "批量采集"),
        ("config_backup", "配置备份"),
    )
    STATUS_CHOICES = (
        ("pending", "等待中"),
        ("running", "运行中"),
        ("success", "成功"),
        ("failed", "失败"),
        ("cancelled", "已取消"),
    )

    celery_task_id = models.CharField(
        max_length=100, unique=True, blank=True, default=None, null=True, verbose_name="Celery任务ID"
    )
    task_type = models.CharField(max_length=50, choices=TASK_TYPES, verbose_name="任务类型")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", verbose_name="状态")
    device = models.ForeignKey(
        "assets.Device", on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks", verbose_name="关联设备"
    )
    params = models.JSONField(default=dict, verbose_name="任务参数")
    result = models.JSONField(null=True, blank=True, verbose_name="任务结果")
    error_message = models.TextField(blank=True, default="", verbose_name="错误信息")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="完成时间")

    class Meta:
        verbose_name = "任务"
        verbose_name_plural = verbose_name
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.get_task_type_display()} - {self.get_status_display()}"

    @property
    def current_stage(self):
        return self.stages.order_by("-created_at").first()

    @property
    def progress(self):
        stages = self.stages.all()
        if not stages:
            return 0
        completed = stages.filter(status__in=["success", "failed", "skipped"]).count()
        return int(completed / stages.count() * 100)


class Stage(models.Model):
    """阶段记录"""

    STAGE_TYPES = (
        ("collection", "数据采集"),
        ("parsing", "配置解析"),
        ("storage", "数据存储"),
    )
    STATUS_CHOICES = (
        ("pending", "等待中"),
        ("running", "运行中"),
        ("success", "成功"),
        ("failed", "失败"),
        ("skipped", "已跳过"),
    )

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="stages", verbose_name="所属任务")
    stage_type = models.CharField(max_length=50, choices=STAGE_TYPES, verbose_name="阶段类型")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", verbose_name="状态")
    input_data = models.JSONField(default=dict, verbose_name="输入数据")
    output_data = models.JSONField(null=True, blank=True, verbose_name="输出数据")
    error_message = models.TextField(blank=True, default="", verbose_name="错误信息")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="完成时间")
    retry_count = models.PositiveIntegerField(default=0, verbose_name="重试次数")
    max_retries = models.PositiveIntegerField(default=3, verbose_name="最大重试次数")

    class Meta:
        verbose_name = "阶段"
        verbose_name_plural = verbose_name
        ordering = ("created_at",)

    def __str__(self):
        return f"{self.task} - {self.get_stage_type_display()} - {self.get_status_display()}"
