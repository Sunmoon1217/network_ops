import secrets
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

from core import task_types


class User(AbstractUser):
    """扩展用户模型。

    ``role`` 是业务角色，与 Django 自带的 ``is_staff`` / ``is_superuser`` 无关：
    - ``normal``   普通用户：登录后只能读（查询）
    - ``operator`` 操作员：登录后可读 + 增删改

    写权限由 ``core.permissions.IsOperatorOrReadOnly`` 判定（``is_superuser`` 恒放行）。
    注册接口只创建 ``normal``；``operator`` 由管理员在 Django admin 里赋给。
    """

    ROLE_CHOICES = (
        ("normal", "普通用户"),
        ("operator", "操作员"),
    )

    phone = models.CharField(max_length=20, blank=True, default="", verbose_name="手机号")
    avatar = models.CharField(max_length=255, blank=True, default="", verbose_name="头像URL")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="normal", verbose_name="角色")

    class Meta:
        verbose_name = "用户"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.username

    @property
    def is_operator(self) -> bool:
        """是否可写（操作员或超管）。"""
        return self.is_superuser or self.role == "operator"


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


class UserPreference(models.Model):
    """按用户保存的前端配置（表格列宽等界面偏好）。

    key 是「页面/表」粒度的命名空间（如 ``table:devices.interfaces:column-widths``），
    value 是任意 JSON（列宽存 ``{列key: 宽度}``）；同一用户的同一 key 只有一行，
    读写都限定在 ``request.user`` 上——偏好不跨用户共享。
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="preferences",
        verbose_name="用户",
    )
    key = models.CharField(max_length=100, verbose_name="偏好键")
    value = models.JSONField(default=dict, verbose_name="偏好值")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "用户偏好"
        verbose_name_plural = verbose_name
        unique_together = ("user", "key")

    def __str__(self):
        return f"{self.user.username} - {self.key}"


class Task(models.Model):
    """任务主记录。

    **作用目标是软引用**：``target_type`` + ``target_id`` 指向任意业务实体（设备、设备组、
    站点…），``target_label`` 是建任务时记下的名字。core 因此不认识任何业务模型，
    也不会被业务表的删除级联带走（见 ``handbook/design/task-framework.md`` §①）。

    ``task_type`` 同样是**自由字符串**，这里刻意不声明 ``choices``：词表属于业务域，由它们
    在 ``core.task_types`` 注册表里登记。``choices`` 是字段的类属性、会写进迁移，运行时
    注册注定与迁移状态漂移——所以词汇不放这里，显示名改由 ``get_task_type_display()``
    反查注册表。
    """

    STATUS_CHOICES = (
        ("pending", "等待中"),
        ("running", "运行中"),
        ("success", "成功"),
        ("failed", "失败"),
        ("cancelled", "已取消"),
    )

    celery_task_id = models.CharField(max_length=100, unique=True, blank=True, default=None, null=True, verbose_name="Celery任务ID")
    task_type = models.CharField(max_length=50, verbose_name="任务类型")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", verbose_name="状态")
    target_type = models.CharField(max_length=50, blank=True, default="", verbose_name="作用目标类型")
    target_id = models.BigIntegerField(null=True, blank=True, verbose_name="作用目标ID")
    target_label = models.CharField(max_length=255, blank=True, default="", verbose_name="作用目标名称")
    params = models.JSONField(default=dict, verbose_name="任务参数")
    result = models.JSONField(null=True, blank=True, verbose_name="任务结果")
    error_message = models.TextField(blank=True, default="", verbose_name="错误信息")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="完成时间")

    if TYPE_CHECKING:
        stages: models.QuerySet["Stage"]

        def get_status_display(self) -> str: ...

    class Meta:
        verbose_name = "任务"
        verbose_name_plural = verbose_name
        ordering = ("-created_at",)
        indexes = (
            # 软引用没有外键索引；按目标查任务（列表过滤、purge 清理）走这个复合索引
            models.Index(fields=("target_type", "target_id"), name="task_target_idx"),
        )

    def __str__(self):
        return f"{self.get_task_type_display()} - {self.get_status_display()}"

    def get_task_type_display(self) -> str:
        """显示名按业务域注册的词汇表反查；未登记的旧词回落 key。

        覆盖 Django 因 ``choices`` 自动生成的同名方法（现在字段没有 ``choices``），
        这样 ``__str__`` / admin / 序列化器都不用改，且 core 里不出现任何业务词汇。
        """
        return task_types.label_for(self.task_type)

    @property
    def device(self) -> int | None:
        """**历史契约**：作用目标是设备时返回设备 ID，否则 ``None``。

        ``Task`` 已经没有 ``device`` 外键了（core 不依赖 assets），但前端还在读
        ``device`` / ``device_hostname`` 这两个键，所以留一对只读的兼容视图：
        哪个 target_type 填它们由注册表说明（``feeds_device_fields``），core 不硬编码
        ``"device"`` 这个词。
        """
        device_type = task_types.device_field_target_type()
        return self.target_id if device_type and self.target_type == device_type else None

    @property
    def device_hostname(self) -> str:
        """**历史契约**：作用目标是设备时返回建任务时记下的设备名，否则空串。"""
        device_type = task_types.device_field_target_type()
        return self.target_label if device_type and self.target_type == device_type else ""

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
    """阶段记录。

    ``stage_type`` 同样是自由字符串，词汇与 handler 由业务域在
    ``core.task_types`` 注册表里登记——core 只负责存储与流转。
    """

    STATUS_CHOICES = (
        ("pending", "等待中"),
        ("running", "运行中"),
        ("success", "成功"),
        ("failed", "失败"),
        ("skipped", "已跳过"),
    )

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="stages", verbose_name="所属任务")
    stage_type = models.CharField(max_length=50, verbose_name="阶段类型")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", verbose_name="状态")
    input_data = models.JSONField(default=dict, verbose_name="输入数据")
    output_data = models.JSONField(null=True, blank=True, verbose_name="输出数据")
    error_message = models.TextField(blank=True, default="", verbose_name="错误信息")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="完成时间")
    retry_count = models.PositiveIntegerField(default=0, verbose_name="重试次数")
    max_retries = models.PositiveIntegerField(default=3, verbose_name="最大重试次数")

    if TYPE_CHECKING:

        def get_status_display(self) -> str: ...

    class Meta:
        verbose_name = "阶段"
        verbose_name_plural = verbose_name
        ordering = ("created_at",)

    def __str__(self):
        return f"{self.task} - {self.get_stage_type_display()} - {self.get_status_display()}"

    def get_stage_type_display(self) -> str:
        """显示名按注册表反查（未登记的旧词回落 key），见 ``Task.get_task_type_display``。"""
        return task_types.label_for(self.stage_type)
