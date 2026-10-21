"""``/api/analysis/queue-status/``：队列积压巡检（只读），前端 Home 页卡片轮询。

采集逻辑全在 ``analysis.queue_monitor``（与 ``manage.py queue_status`` 同源）；
本视图只做透传。每次请求都是几个 O(1) 的 Redis 命令，30s 轮询无压力。

**只读、只报警、不干预**：背压是生产者侧的事（``access_stream.backlog``），
监控端绝不在这里删消息 / 清队列。
"""

from rest_framework.decorators import api_view
from rest_framework.response import Response

from analysis.queue_monitor import collect


@api_view(["GET"])
def queue_status(request):
    return Response(collect())
