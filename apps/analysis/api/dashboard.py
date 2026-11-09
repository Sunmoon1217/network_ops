"""Dashboard 大屏的只读接口（挂在 ``/api/dashboard/``）。

响应包装是**旧 dashboard 前端 axios 拦截器的硬要求**（``return res.result``，见
``frontend/src/dashboard/api/dashboard_api.ts``）；本项目其它接口是裸 DRF Response，
这里是唯一例外，等前端统一后再改回裸数组。

查询参数 ``panel`` / ``group`` / ``name`` 对齐旧 ``getdashboard``。当前值直接读
``DashboardMetric``；``group=linechart`` 或 ``name=bandwidth-*`` 时，把 ``MetricSample``
最近 3 小时的链路样本聚合成「一行一个时间点」的 EAV 视图，前端 ``ChartsCard-1``
无需改动即可消费。写入口是 analysis 的写库任务（由 ingest 采集任务按任务名投递），
本模块只读。
"""

from datetime import timedelta

from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from analysis.models import DashboardMetric, MetricSample

LINECHART_HOURS = 3


def _envelope(result):
    """包成 ``{status, message, result}``：旧前端拦截器只取 ``res.result``。"""
    return Response({"status": 200, "message": "ok", "result": result})


def _metric_row(metric):
    return {
        "id": metric.pk,
        "panel": metric.panel,
        "group": metric.group,
        "name": metric.name,
        "value": metric.value,
        "list_value": metric.list_value,
    }


def _linechart_rows():
    """规范化时序样本 → 前端期望的 ``{time, data:{ipv4:{...}, fwlink:{...}}}`` 行。

    时间用 aware 的 ``sampled_at`` 按本地时区格式化（``USE_TZ=True``），``name`` 统一
    成短横线形式 ``bandwidth-HH:MM``，与 ``getlinklatest`` 的查询对齐；旧后端写的
    ``bandwidth_{time}``（下划线、且 time 是整条时间轴 dict）查不到。
    """
    since = timezone.now() - timedelta(hours=LINECHART_HOURS)
    samples = (
        MetricSample.objects.filter(kind="link_bandwidth", sampled_at__gte=since)
        .order_by("sampled_at")
        .values_list("sampled_at", "scope", "subject", "value")
    )

    points: dict = {}
    for sampled_at, scope, subject, value in samples:
        label = timezone.localtime(sampled_at).strftime("%H:%M")
        point = points.setdefault(sampled_at, {"time": label, "data": {}})
        point["data"].setdefault(scope, {})[subject] = value

    return [
        {
            "id": index,
            "panel": "link",
            "group": "linechart",
            "name": f"bandwidth-{point['time']}",
            "value": None,
            "list_value": [point],
        }
        for index, point in enumerate(points.values())
    ]


@api_view(["GET"])
def dashboard(request):
    """``GET /api/dashboard/?panel=&group=&name=`` → ``DashboardData[]``（带旧包装）。"""
    panel = request.query_params.get("panel")
    group = request.query_params.get("group")
    name = request.query_params.get("name")

    metrics = DashboardMetric.objects.all()
    if panel:
        metrics = metrics.filter(panel=panel)
    if group:
        metrics = metrics.filter(group=group)
    if name:
        metrics = metrics.filter(name=name)

    result = [_metric_row(metric) for metric in metrics]

    wants_linechart = (not panel or panel == "link") and (group == "linechart" or (name and name.startswith("bandwidth-")))
    if wants_linechart:
        points = _linechart_rows()
        if name:
            points = [point for point in points if point["name"] == name]
        result.extend(points)

    return _envelope(result)
