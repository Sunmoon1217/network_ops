"""任务与阶段的序列化器。

``Task`` 的写入只开放 ``device`` / ``task_type`` / ``params``——状态、结果、时间戳都由
工作流（``ops.workflow``）与阶段任务维护，客户端不该直接改。
"""

from rest_framework import serializers

from core.models import Stage, Task


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
        """建任务即投递第一个阶段（采集），见 ``ops.workflow.start_task``。"""
        from ops.workflow import start_task

        return start_task(
            device=validated_data["device"],
            task_type=validated_data["task_type"],
            params=validated_data.get("params") or {},
        )
