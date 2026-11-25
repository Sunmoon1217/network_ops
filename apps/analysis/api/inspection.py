"""巡检接口：日指标只读（``inspection-devices/``、``inspection-interfaces/``）、批次只读
（``inspection-runs/``）与带宽采集目标增删改查（``inspection-targets/``）。

日指标写入只有 ``analysis.write_inspection`` 一个入口；大屏免认证的数据不在这里，而是由写库任务
物化到 ``DashboardMetric(inspection/device/list)``。``?date=`` 缺省取最新有数据的那天。
"""

from datetime import date
from statistics import fmean

from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from analysis.models import DeviceMetricDaily, InspectionRun, InspectionTarget, InterfaceMetricDaily


class InspectionTargetSerializer(serializers.ModelSerializer):
    """接口带宽采集目标：itemids 留空时采集器按主机名 + 接口名自动搜索监控项。"""

    class Meta:
        model = InspectionTarget
        fields = ("id", "host", "ifname", "itemids", "enabled", "updated_at")
        read_only_fields = ("updated_at",)

    def validate_itemids(self, value):
        """只接受字符串数组，去空白；其他类型直接报错。"""
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise serializers.ValidationError("必须是字符串数组")
        return [item.strip() for item in value if item.strip()]


class InspectionRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = InspectionRun
        fields = ("id", "date", "status", "device_count", "interface_count", "error", "started_at", "finished_at")


class DeviceMetricDailySerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceMetricDaily
        fields = ("id", "date", "host", "cpu_avg", "cpu_max", "memory_avg", "memory_max", "updated_at")


class InterfaceMetricDailySerializer(serializers.ModelSerializer):
    class Meta:
        model = InterfaceMetricDaily
        fields = (
            "id",
            "date",
            "host",
            "ifname",
            "in_bps_avg",
            "in_bps_max",
            "out_bps_avg",
            "out_bps_max",
            "in_usage_avg",
            "in_usage_max",
            "out_usage_avg",
            "out_usage_max",
            "updated_at",
        )


def _parse_date(raw: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise ValidationError({"date": "必须是 YYYY-MM-DD"}) from None


def _date_filter(queryset, model, raw: str | None):
    """给了 date 就按天过滤，否则只返回该模型最新有数据的一天。"""
    if raw:
        return queryset.filter(date=_parse_date(raw))
    latest = model.objects.order_by("-date").values_list("date", flat=True).first()
    return queryset.filter(date=latest) if latest else queryset.none()


class DeviceMetricDailyViewSet(viewsets.ReadOnlyModelViewSet):
    """设备 CPU / 内存日指标；支持 ``?date=`` 与 ``?host=``（模糊）。"""

    serializer_class = DeviceMetricDailySerializer
    search_fields = ("host",)
    ordering_fields = ("date", "host", "cpu_avg", "cpu_max", "memory_avg", "memory_max")

    def get_queryset(self):
        queryset = _date_filter(DeviceMetricDaily.objects.all(), DeviceMetricDaily, self.request.query_params.get("date"))
        host = self.request.query_params.get("host")
        if host:
            queryset = queryset.filter(host__icontains=host)
        return queryset

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """当天概览：设备数、CPU / 内存均值与 CPU 峰值 TOP5。"""
        queryset = self.get_queryset()
        day = queryset.order_by("-date").values_list("date", flat=True).first()
        rows = list(queryset.values("host", "cpu_avg", "cpu_max", "memory_avg", "memory_max"))
        cpu_avgs = [row["cpu_avg"] for row in rows if row["cpu_avg"] is not None]
        mem_avgs = [row["memory_avg"] for row in rows if row["memory_avg"] is not None]
        top = sorted(rows, key=lambda row: row["cpu_max"] if row["cpu_max"] is not None else -1.0, reverse=True)[:5]
        return Response(
            {
                "date": day.isoformat() if day else None,
                "device_count": len(rows),
                "cpu_avg": round(fmean(cpu_avgs), 2) if cpu_avgs else None,
                "memory_avg": round(fmean(mem_avgs), 2) if mem_avgs else None,
                "cpu_top": [{"name": row["host"], "cpu_max": row["cpu_max"]} for row in top],
            }
        )


class InterfaceMetricDailyViewSet(viewsets.ReadOnlyModelViewSet):
    """接口带宽日指标；支持 ``?date=`` 与 ``?host=``（模糊）。"""

    serializer_class = InterfaceMetricDailySerializer
    search_fields = ("host", "ifname")
    ordering_fields = ("date", "host", "ifname", "in_bps_max", "out_bps_max", "in_usage_max", "out_usage_max")

    def get_queryset(self):
        queryset = _date_filter(InterfaceMetricDaily.objects.all(), InterfaceMetricDaily, self.request.query_params.get("date"))
        host = self.request.query_params.get("host")
        if host:
            queryset = queryset.filter(host__icontains=host)
        return queryset


class InspectionRunViewSet(viewsets.ReadOnlyModelViewSet):
    """巡检批次：每日一条，记录成功 / 失败与采集条数，作为数据新鲜度来源。"""

    queryset = InspectionRun.objects.all()
    serializer_class = InspectionRunSerializer
    ordering_fields = ("date", "status", "device_count", "interface_count")


class InspectionTargetViewSet(viewsets.ModelViewSet):
    """带宽采集目标：读开放给已认证用户，写限 operator 或超管（全局权限默认值）。"""

    queryset = InspectionTarget.objects.all()
    serializer_class = InspectionTargetSerializer
    search_fields = ("host", "ifname")
    ordering_fields = ("host", "ifname", "enabled", "updated_at")
