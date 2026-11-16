"""任务与阶段的 API：任务支持列表 / 详情 / 新建 / 取消，阶段只读。

状态由 celery 阶段任务与业务域推进信号维护，接口不开放改状态。见 ``handbook/tasks.md``。
"""

import logging

from rest_framework import mixins, viewsets
from rest_framework import status as http_status
from rest_framework.decorators import action
from rest_framework.response import Response

from core import task_types
from core.models import Stage, Task

from .serializers import StageSerializer, TaskSerializer

logger = logging.getLogger(__name__)


class TaskViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """任务：列表 / 详情 / 新建（即投递首个阶段） / 取消。"""

    queryset = Task.objects.prefetch_related("stages").all()
    serializer_class = TaskSerializer
    # 作用目标的名字在 target_label 里（建任务时记下），不必 join 业务表
    search_fields = ("target_label",)
    ordering_fields = ("created_at", "started_at", "completed_at", "status")

    def get_queryset(self):
        """手工做精确过滤：``device=<id>`` 折算成软引用查询，其余按字段直筛。"""
        qs = super().get_queryset()
        device = self.request.query_params.get("device")
        if device:
            device_type = task_types.device_field_target_type()
            if device_type:
                qs = qs.filter(target_type=device_type, target_id=device)
            else:
                qs = qs.none()  # 没有业务域声明设备类型，按设备过滤必然无结果
        target_type = self.request.query_params.get("target_type")
        if target_type:
            qs = qs.filter(target_type=target_type)
        task_status = self.request.query_params.get("status")
        if task_status:
            qs = qs.filter(status=task_status)
        task_type = self.request.query_params.get("task_type")
        if task_type:
            qs = qs.filter(task_type=task_type)
        return qs

    def create(self, request, *args, **kwargs):
        """新建任务并投递异步执行；投递失败（broker 不可达）返回 503 而不是 500。"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            task = serializer.save()
        except Exception as e:
            logger.exception("创建任务失败")
            return Response(
                {"error": f"创建任务失败: {e}"},
                status=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(self.get_serializer(task).data, status=http_status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        task = self.get_object()
        if task.status in ("success", "failed", "cancelled"):
            return Response(
                {"error": f"任务已{task.get_status_display()}，无法取消"},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        from core.tasks import cancel

        cancel(task)
        task.refresh_from_db()
        return Response(self.get_serializer(task).data)


class StageViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """阶段：只读。用于按任务/类型/状态排查某一步卡在哪里。"""

    queryset = Stage.objects.select_related("task").all()
    serializer_class = StageSerializer
    search_fields = ("task__target_label", "error_message")
    ordering_fields = ("created_at", "started_at", "completed_at", "status")

    def get_queryset(self):
        qs = super().get_queryset()
        task = self.request.query_params.get("task")
        if task:
            qs = qs.filter(task_id=task)
        stage_type = self.request.query_params.get("stage_type")
        if stage_type:
            qs = qs.filter(stage_type=stage_type)
        stage_status = self.request.query_params.get("status")
        if stage_status:
            qs = qs.filter(status=stage_status)
        return qs
