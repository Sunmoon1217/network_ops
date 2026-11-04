"""运行监控的只读端点：队列积压 / Redis 服务状态 / Celery worker 与任务 / Stream 消息摘要。

视图分别透传 ``analysis`` 的采集模块（与命令行同源），前端「任务中心 → 运行监控」页
与 Home 页卡片轮询。所有采集都是只读 O(1)（celery 侧是带超时的 inspect 广播），
30s 轮询无压力。

**只读、只报警、不干预**：背压是生产者侧的事（``access_stream.backlog``），
取消/撤销任务走 ``/api/tasks/<id>/cancel/``；监控端绝不在这里删消息 / 清队列 /
revoke 任务。
"""

from rest_framework.decorators import api_view
from rest_framework.response import Response

from analysis import celery_monitor, redis_monitor
from analysis.queue_monitor import collect, message_detail


@api_view(["GET"])
def queue_status(request):
    return Response(collect())


@api_view(["GET"])
def queue_message_detail(request, message_id: str):
    """按消息 ID 取 Stream 消息摘要（只读）：运行监控「重投最多的消息」点开看内容。

    只回摘要（设备 / 载荷大小 / 组合数 / 前 N 条 key），**不整条回传载荷**——一条消息
    最坏几十 MB；载荷过大时只报大小（truncated=True），原文走 redis-cli XRANGE。
    """
    try:
        sample = int(request.query_params.get("sample", 10))
    except ValueError:
        sample = 10
    detail = message_detail(message_id, sample=sample)
    if not detail["exists"]:
        return Response({"detail": f"消息 {message_id} 不存在（已被 trim / XDEL，或 ID 不对）"}, status=404)
    return Response(detail)


@api_view(["GET"])
def redis_status(request):
    """Redis 服务状态（INFO 口径）：内存 / 连接 / 命中率 / 键空间 / 运行时长。"""
    return Response(redis_monitor.collect())


@api_view(["GET"])
def celery_status(request):
    """Celery worker 与任务：worker 名单 / 执行中 / 排队 / 延迟（inspect 口径）。"""
    return Response(celery_monitor.collect())
