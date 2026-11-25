from django.contrib import admin

from .models import (
    AccessFlow,
    DeviceMetricDaily,
    InspectionConfig,
    InspectionDeviceTarget,
    InspectionRun,
    InspectionTarget,
    InterfaceMetricDaily,
    InternetAnalysis,
)


@admin.register(InternetAnalysis)
class InternetAnalysisAdmin(admin.ModelAdmin):
    # result 是整份分析结果的大 JSON，不进列表；详情页查看
    list_display = ("id", "device", "duration_ms", "analyzed_at")
    list_filter = (("device", admin.RelatedOnlyFieldListFilter), "analyzed_at")
    search_fields = ("device__hostname",)
    autocomplete_fields = ("device",)
    list_select_related = ("device",)
    date_hierarchy = "analyzed_at"


@admin.register(AccessFlow)
class AccessFlowAdmin(admin.ModelAdmin):
    """访问流是策略展开的派生缓存（由 rebuild 任务幂等重建），这里只读。"""

    # contexts / device_ids / policy_ids 是大 JSON，不进列表；详情页只读查看
    list_display = (
        "id",
        "src_ip",
        "src_prefix",
        "src_range_end",
        "dst_ip",
        "dst_prefix",
        "dst_range_end",
        "protocol",
        "port",
        "port2",
        "action",
        "updated_at",
    )
    list_filter = ("action", "protocol", "created_at")
    search_fields = ("src_ip", "dst_ip")
    list_per_page = 50
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # 返回 False 不挡查看：GET 详情/列表照常，只是表单只读、不可保存
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(InspectionConfig)
class InspectionConfigAdmin(admin.ModelAdmin):
    """巡检配置单例：时间点与采集时段，也可在「巡检」页修改。"""

    list_display = ("id", "schedule_hour", "schedule_minute", "window_start", "window_end", "last_dispatch_date")
    readonly_fields = ("last_dispatch_date", "updated_at")


@admin.register(InspectionDeviceTarget)
class InspectionDeviceTargetAdmin(admin.ModelAdmin):
    """设备巡检对象：CPU / 内存采集的主机清单，人工维护。"""

    list_display = ("id", "host", "enabled", "updated_at")
    list_filter = ("enabled",)
    search_fields = ("host",)
    list_editable = ("enabled",)


@admin.register(InspectionTarget)
class InspectionTargetAdmin(admin.ModelAdmin):
    """接口带宽巡检目标：采集器的输入清单，人工维护。"""

    list_display = ("id", "host", "ifname", "enabled", "updated_at")
    list_filter = ("enabled",)
    search_fields = ("host", "ifname")
    list_editable = ("enabled",)


@admin.register(InspectionRun)
class InspectionRunAdmin(admin.ModelAdmin):
    """巡检批次：由每日任务写入，这里只读。"""

    list_display = ("id", "date", "status", "device_count", "interface_count", "finished_at")
    list_filter = ("status",)
    date_hierarchy = "date"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(DeviceMetricDaily)
class DeviceMetricDailyAdmin(admin.ModelAdmin):
    list_display = ("id", "date", "host", "cpu_avg", "cpu_max", "memory_avg", "memory_max")
    search_fields = ("host",)
    date_hierarchy = "date"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(InterfaceMetricDaily)
class InterfaceMetricDailyAdmin(admin.ModelAdmin):
    list_display = (
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
    )
    search_fields = ("host", "ifname")
    date_hierarchy = "date"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
