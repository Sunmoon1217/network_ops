"""任务与阶段的 API。

只提供「列表 / 详情 / 新建 / 取消」与阶段的只读查询：任务的推进完全由 celery 阶段任务
与 ``ingest/signals.py`` 的信号负责，接口不该能随意改状态（否则数据库里的 Task/Stage 会与
真实的 celery 执行状态脱节）。
"""

import logging

from rest_framework import mixins, viewsets
from rest_framework import status as http_status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Stage, Task

from .serializers import StageSerializer, TaskSerializer

logger = logging.getLogger(__name__)


class TaskViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """任务：列表 / 详情 / 新建（即投递采集阶段） / 取消。"""

    queryset = Task.objects.select_related("device").prefetch_related("stages").all()
    serializer_class = TaskSerializer
    permission_classes = (IsAuthenticated,)
    search_fields = ("device__hostname",)
    ordering_fields = ("created_at", "started_at", "completed_at", "status")

    def get_queryset(self):
        """手工过滤：项目只启用了 SearchFilter / OrderingFilter，精确过滤按惯例在这里做。"""
        qs = super().get_queryset()
        device = self.request.query_params.get("device")
        if device:
            qs = qs.filter(device_id=device)
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

        from ingest.workflow import cancel_task

        cancel_task(task)
        task.refresh_from_db()
        return Response(self.get_serializer(task).data)


class StageViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """阶段：只读。用于按任务/类型/状态排查某一步卡在哪里。"""

    queryset = Stage.objects.select_related("task", "task__device").all()
    serializer_class = StageSerializer
    permission_classes = (IsAuthenticated,)
    search_fields = ("task__device__hostname", "error_message")
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
