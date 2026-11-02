"""运行监控的只读端点：队列积压 / Redis 服务状态 / Celery worker 与任务。

三个视图分别透传 ``analysis`` 三个采集模块（与命令行同源），前端「任务中心 →
运行监控」页与 Home 页卡片轮询。所有采集都是只读 O(1)（celery 侧是带超时的
inspect 广播），30s 轮询无压力。

**只读、只报警、不干预**：背压是生产者侧的事（``access_stream.backlog``），
取消/撤销任务走 ``/api/tasks/<id>/cancel/``；监控端绝不在这里删消息 / 清队列 /
revoke 任务。
"""

from rest_framework.decorators import api_view
from rest_framework.response import Response

from analysis import celery_monitor, redis_monitor
from analysis.queue_monitor import collect


@api_view(["GET"])
def queue_status(request):
    return Response(collect())


@api_view(["GET"])
def redis_status(request):
    """Redis 服务状态（INFO 口径）：内存 / 连接 / 命中率 / 键空间 / 运行时长。"""
    return Response(redis_monitor.collect())


@api_view(["GET"])
def celery_status(request):
    """Celery worker 与任务：worker 名单 / 执行中 / 排队 / 延迟（inspect 口径）。"""
    return Response(celery_monitor.collect())
