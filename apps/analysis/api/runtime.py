"""运行监控的只读端点：队列积压 / Redis 状态 / Celery worker 与任务，分别透传三个采集模块。

只读、只报警、不干预：背压归生产者，取消任务走 ``/api/core/tasks/<id>/cancel/``。
"""

from rest_framework.decorators import api_view
from rest_framework.response import Response

from analysis.monitor import celery, redis
from analysis.monitor.queue import collect


@api_view(["GET"])
def queue_status(request):
    return Response(collect())


@api_view(["GET"])
def redis_status(request):
    """Redis 服务状态（INFO 口径）：内存 / 连接 / 命中率 / 键空间 / 运行时长。"""
    return Response(redis.collect())


@api_view(["GET"])
def celery_status(request):
    """Celery worker 与任务：worker 名单 / 执行中 / 排队 / 延迟（inspect 口径）。"""
    return Response(celery.collect())
