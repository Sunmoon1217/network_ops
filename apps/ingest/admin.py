# -*- coding: utf-8 -*-
from django.contrib import admin

from .models import AccessFlow


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
