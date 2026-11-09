"""Dashboard 大屏的只读接口（挂在 ``/api/dashboard/``）。

大屏是无人值守的展示页（``dashboard.html`` 独立入口），**不依赖登录态**：这里两个
视图都显式 ``AllowAny``，前端不带 Token，也不该被 401 重定向到登录页。机柜数据同样
走本模块的专用只读接口，而不是需要登录的 assets ModelViewSet。

响应包装是**大屏前端的历史契约**（``{status, message, result}``，见
``frontend/src/shared/api/dashboard.ts`` 里显式取 ``data.result``）；本项目其它接口是
裸 DRF Response，这里是唯一例外，等前端统一后再改回裸数组。

查询参数 ``panel`` / ``group`` / ``name`` 对齐旧 ``getdashboard``。当前值直接读
``DashboardMetric``；``group=linechart`` 或 ``name=bandwidth-*`` 时，把 ``MetricSample``
最近 3 小时的链路样本聚合成「一行一个时间点」的 EAV 视图，前端 ``ChartsCard-1``
无需改动即可消费。写入口是 analysis 的写库任务（由 ingest 采集任务按任务名投递），
本模块只读。
"""

from datetime import timedelta

from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from analysis.models import DashboardMetric, MetricSample
from assets.models import Cabinet, Device

LINECHART_HOURS = 3


def _envelope(result):
    """包成 ``{status, message, result}``：大屏前端显式取 ``data.result``。"""
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
@permission_classes([AllowAny])
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


@api_view(["GET"])
@permission_classes([AllowAny])
def dashboard_cabinets(request):
    """``GET /api/dashboard/cabinets/`` → 机柜 U 位视图所需字段（免认证只读）。

    大屏机柜面板原本读 ``/api/assets/cabinets/`` 与 ``/api/assets/devices/``，这两个
    ModelViewSet 走全局权限（GET 也要登录）。这里只投影画 U 位和标签必需的字段，
    不返回账号、SNMP/口令、备注等数据，让大屏在无人登录时也能完整展示。
    """
    cabinet_rows = Cabinet.objects.values(
        "id", "name", "row", "total_u", "status", "room__name", "room__datacenter__name"
    ).order_by("room__datacenter__name", "room__name", "name")
    cabinets = [
        {
            "id": row["id"],
            "name": row["name"],
            "row": row["row"],
            "total_u": row["total_u"],
            "status": row["status"],
            "room_name": row["room__name"],
            "datacenter_name": row["room__datacenter__name"],
        }
        for row in cabinet_rows
    ]

    type_labels = dict(Device.DEVICE_TYPE_CHOICES)
    device_rows = Device.objects.filter(cabinet__isnull=False, u_position__isnull=False).values(
        "id", "hostname", "cabinet_id", "u_position", "height", "ip_address", "device_type"
    ).order_by("hostname")
    devices = [
        {
            "id": row["id"],
            "hostname": row["hostname"],
            "cabinet": row["cabinet_id"],
            "u_position": row["u_position"],
            "height": row["height"],
            "ip_address": row["ip_address"],
            "device_type": row["device_type"],
            "device_type_display": type_labels.get(row["device_type"], row["device_type"]),
        }
        for row in device_rows
    ]

    return _envelope({"cabinets": cabinets, "devices": devices})
