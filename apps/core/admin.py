# -*- coding: utf-8 -*-
from django.contrib import admin

from .models import Stage, Task, Token, User, UserPreference

admin.site.site_header = "网络运维管理平台"
admin.site.site_title = "网络运维管理平台"
admin.site.index_title = "后台管理"


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    # 密码哈希不进列表（无管理价值还平白暴露一列），改看 username / 联系方式
    list_display = (
        "id",
        "username",
        "first_name",
        "last_name",
        "email",
        "phone",
        "is_staff",
        "is_superuser",
        "is_active",
        "date_joined",
        "last_login",
    )
    list_filter = (
        "last_login",
        "is_superuser",
        "is_staff",
        "is_active",
        "date_joined",
    )
    search_fields = ("username", "first_name", "last_name", "email", "phone")
    # 组 / 权限是有限集合，双栏选择比手填 id 的 raw_id_fields 好用
    filter_horizontal = ("groups", "user_permissions")


@admin.register(Token)
class TokenAdmin(admin.ModelAdmin):
    # 完整 key 不进列表（等同口令），列表只露前 8 位，详情页可复制完整的
    list_display = ("id", "user", "masked_key", "created")
    list_filter = (("user", admin.RelatedOnlyFieldListFilter), "created")
    search_fields = ("key", "user__username")
    list_select_related = ("user",)

    @admin.display(description="Token Key")
    def masked_key(self, obj):
        return f"{obj.key[:8]}…"


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "key", "updated_at")
    list_filter = (("user", admin.RelatedOnlyFieldListFilter), "updated_at")
    search_fields = ("user__username", "key")
    autocomplete_fields = ("user",)
    list_select_related = ("user",)
    date_hierarchy = "updated_at"


class StageInline(admin.TabularInline):
    """阶段由 Celery 工作流写入，这里只读展示（且不渲染可能存着配置全文的输入/输出）。"""

    model = Stage
    extra = 0
    can_delete = False
    fields = (
        "stage_type",
        "status",
        "retry_count",
        "max_retries",
        "created_at",
        "started_at",
        "completed_at",
        "error_message",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "task_type",
        "status",
        "device",
        "celery_task_id",
        "created_at",
        "started_at",
        "completed_at",
    )
    list_filter = (
        "task_type",
        "status",
        ("device", admin.RelatedOnlyFieldListFilter),
        "created_at",
    )
    search_fields = ("device__hostname", "celery_task_id", "error_message")
    autocomplete_fields = ("device",)
    list_select_related = ("device",)
    date_hierarchy = "created_at"
    inlines = (StageInline,)


@admin.register(Stage)
class StageAdmin(admin.ModelAdmin):
    # 输入/输出数据可能存着配置全文，不进列表；详情页再看
    list_display = (
        "id",
        "task",
        "stage_type",
        "status",
        "retry_count",
        "max_retries",
        "created_at",
        "completed_at",
    )
    list_filter = ("stage_type", "status", "created_at")
    search_fields = ("task__device__hostname", "task__celery_task_id", "error_message")
    autocomplete_fields = ("task",)
    list_select_related = ("task",)
    date_hierarchy = "created_at"
