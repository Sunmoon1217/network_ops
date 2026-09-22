"""注册与任务相关的序列化器。

``Task`` 的写入只开放 ``device`` / ``task_type`` / ``params``——状态、结果、时间戳都由
工作流（``ingest.workflow``）与阶段任务维护，客户端不该直接改。
"""

from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from core.models import Stage, Task, User


class RegisterSerializer(serializers.Serializer):
    """注册入参 → 新用户（**只**创建普通账号）。

    - 只开放 ``username`` / ``password`` / ``email`` / ``phone``：``is_staff``、``is_superuser``、
      ``is_active`` 一律由服务端决定，注册出来的账号没有任何管理权限（见 ``create()`` 用
      ``create_user`` 而不是 ``create_superuser``）。
    - 密码交给 Django 的 ``AUTH_PASSWORD_VALIDATORS`` 那四条规则（与 ``createsuperuser`` /
      ``changepassword`` 完全同一套），所以「太短 / 纯数字 / 与用户名相似 / 常见密码」都会在这里被拒。
    - ``email`` / ``phone`` 可选：``AbstractUser.email`` 本身不是 unique，这里也不做强唯一约束
      （同一个人可能有多个账号），但邮箱要过 ``EmailField`` 校验。
    - 用户名用 ``iexact`` 判重：数据库层是**大小写敏感**的唯一约束，只查 ``exact`` 会放过
      ``Admin``／``admin`` 这种极易混淆的并存账号。
    """

    username = serializers.CharField(
        max_length=150,
        validators=[UnicodeUsernameValidator()],
        help_text="字母、数字与 @ . + - _ 组成的用户名",
    )
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")

    def validate_username(self, value: str) -> str:
        username = value.strip()
        if not username:
            raise serializers.ValidationError("用户名不能为空")
        if User.objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError("该用户名已被占用")
        return username

    def validate(self, attrs):
        """密码校验要带上「候选用户」：``UserAttributeSimilarityValidator`` 会拿 username / email 比对。"""
        candidate = User(username=attrs.get("username", ""), email=attrs.get("email", ""))
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class ChangePasswordSerializer(serializers.Serializer):
    """修改密码序列化器"""

    old_password = serializers.CharField(
        required=True,
        write_only=True,
        error_messages={
            "required": "请输入原密码",
            "blank": "原密码不能为空",
        },
    )
    new_password = serializers.CharField(
        required=True,
        write_only=True,
        min_length=8,
        error_messages={
            "required": "请输入新密码",
            "blank": "新密码不能为空",
            "min_length": "新密码长度不能少于 8 位",
        },
    )
    confirm_password = serializers.CharField(
        required=True,
        write_only=True,
        error_messages={
            "required": "请再次输入新密码",
            "blank": "确认密码不能为空",
        },
    )

    def validate_old_password(self, value):
        """校验原密码是否正确"""
        if self.instance and not self.instance.check_password(value):
            raise serializers.ValidationError("原密码不正确")
        return value

    def validate_new_password(self, value):
        """校验新密码强度"""
        user = self.instance
        try:
            validate_password(value, user)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value

    def validate(self, attrs):
        """跨字段校验"""
        old_password = attrs.get("old_password")
        new_password = attrs.get("new_password")
        confirm_password = attrs.get("confirm_password")

        # 两次新密码一致
        if new_password != confirm_password:
            raise serializers.ValidationError({"confirm_password": "两次输入的新密码不一致"})

        # 新旧密码不能相同
        if old_password == new_password:
            raise serializers.ValidationError({"new_password": "新密码不能与原密码相同"})

        return attrs

    def update(self, instance, validated_data):
        instance.set_password(validated_data["new_password"])
        instance.save(update_fields=["password"])
        return instance


class StageSerializer(serializers.ModelSerializer):
    stage_type_display = serializers.CharField(source="get_stage_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Stage
        fields = (
            "id",
            "task",
            "stage_type",
            "stage_type_display",
            "status",
            "status_display",
            "input_data",
            "output_data",
            "error_message",
            "created_at",
            "started_at",
            "completed_at",
            "retry_count",
            "max_retries",
        )
        # 阶段记录由 celery 任务维护，接口只读
        read_only_fields = fields


class TaskSerializer(serializers.ModelSerializer):
    device_hostname = serializers.CharField(source="device.hostname", read_only=True)
    task_type_display = serializers.CharField(source="get_task_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    progress = serializers.IntegerField(read_only=True)
    stages = StageSerializer(many=True, read_only=True)

    class Meta:
        model = Task
        fields = (
            "id",
            "device",
            "device_hostname",
            "task_type",
            "task_type_display",
            "status",
            "status_display",
            "params",
            "result",
            "error_message",
            "progress",
            "created_at",
            "started_at",
            "completed_at",
            "stages",
        )
        read_only_fields = (
            "id",
            "device_hostname",
            "task_type_display",
            "status",
            "status_display",
            "result",
            "error_message",
            "progress",
            "created_at",
            "started_at",
            "completed_at",
            "stages",
        )

    def create(self, validated_data):
        """建任务即投递第一个阶段（采集），见 ``ingest.workflow.start_task``。"""
        from ingest.workflow import start_task

        return start_task(
            device=validated_data["device"],
            task_type=validated_data["task_type"],
            params=validated_data.get("params") or {},
        )
