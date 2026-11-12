"""Dashboard 大屏的只读接口（挂在 ``/api/dashboard/``）。

大屏是无人值守的展示页（``dashboard.html`` 独立入口），**不依赖登录态**：这里两个
视图都显式 ``AllowAny``，前端不带 Token，也不该被 401 重定向到登录页。机柜数据同样
走本模块的专用只读接口，而不是需要登录的 assets ModelViewSet。

响应包装是**大屏前端的历史契约**（``{status, message, result}``，见
``frontend/src/shared/api/dashboard.ts`` 里显式取 ``data.result``）；本项目其它接口是
裸 DRF Response，这里是唯一例外，等前端统一后再改回裸数组。

查询参数 ``panel`` / ``group`` / ``name`` 对齐旧 ``getdashboard``。``DashboardMetric``
仍然服务设备状态 / 工单 / SLB / 巡检；``group=linechart`` 或 ``name=bandwidth-*`` 时
**不再读 MetricSample**，而是读 ingest 侧刷新进 Redis 的链路缓存（``link_cache``），
把完整结果拼回旧 EAV 行视图，并把脱敏的面板 / scope / target label 放在响应的
``meta`` 里（前端 ``LinkBandwidthWidget`` 一次请求拿全，前端零改动消费数据部分）。
写入口是 ingest 的 ``refresh_link_cache``，本模块只读。
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from analysis.models import DashboardMetric
from assets.models import Cabinet, Device
from ingest.collectors.link_cache import empty_link_payload, read_link_cache


def _envelope(result, meta=None):
    """包成 ``{status, message, result}``：大屏前端显式取 ``data.result``。

    ``meta`` 只给链路 linechart 分支（面板 / scope / target label），其它接口
    不带这个键，响应形状保持不变。
    """
    body = {"status": 200, "message": "ok", "result": result}
    if meta is not None:
        body["meta"] = meta
    return Response(body)


def _metric_row(metric):
    return {
        "id": metric.pk,
        "panel": metric.panel,
        "group": metric.group,
        "name": metric.name,
        "value": metric.value,
        "list_value": metric.list_value,
    }


def _link_points(payload, name=None):
    """缓存 payload → 旧 EAV 行视图 ``bandwidth-HH:MM``（前端数据形状零改动）。"""
    points = [
        {
            "id": index,
            "panel": "link",
            "group": "linechart",
            "name": f"bandwidth-{point.get('time', '')}",
            "value": None,
            "list_value": [point],
        }
        for index, point in enumerate(payload.get("points") or [])
    ]
    if name:
        points = [point for point in points if point["name"] == name]
    return points


def _link_meta(payload):
    """缓存里的展示字段（采集侧已脱敏，不含 host / ifname）。"""
    return {
        "panels": payload.get("panels") or [],
        "scopes": payload.get("scopes") or {},
        "targets": payload.get("targets") or [],
        "window_hours": payload.get("window_hours"),
        "refreshed_at": payload.get("refreshed_at"),
    }


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
        payload = read_link_cache()
        if payload is None:
            # 缓存未生成 / Redis 不可用：下发静态 meta 空壳（不造数值），前端据此画空图框
            payload = empty_link_payload()
        result.extend(_link_points(payload, name))
        return _envelope(result, meta=_link_meta(payload))

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
