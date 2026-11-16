# -*- coding: utf-8 -*-
from django.contrib import admin

from . import task_types
from .models import Stage, Task, Token, User, UserPreference

admin.site.site_header = "网络运维管理平台"
admin.site.site_title = "网络运维管理平台"
admin.site.index_title = "后台管理"


class VocabularyListFilter(admin.SimpleListFilter):
    """按 ``core.task_types`` 的注册表快照出过滤项。

    模型字段已经去掉 ``choices``（词汇属于业务域，写进迁移会永久漂移），admin 若仍写
    ``list_filter = ("task_type",)`` 会退化成「按库里出现过的一切字符串过滤」。这里改成
    运行期读注册表：选项带中文标签，业务域新登记的词自动出现，且不产生任何迁移。
    """

    def vocabulary(self) -> list[tuple[str, str]]:
        raise NotImplementedError

    def lookups(self, request, model_admin):
        return list(self.vocabulary())

    def queryset(self, request, queryset):
        value = self.value()
        # 只认注册表里的词；未登记的值（历史脏数据）不当作可选项，但也别让过滤静默失效
        if value and value in dict(self.vocabulary()):
            return queryset.filter(**{self.parameter_name: value})
        return queryset


class TaskTypeFilter(VocabularyListFilter):
    title = "任务类型"
    parameter_name = "task_type"

    def vocabulary(self):
        return task_types.task_type_choices()


class StageTypeFilter(VocabularyListFilter):
    title = "阶段类型"
    parameter_name = "stage_type"

    def vocabulary(self):
        return task_types.stage_type_choices()


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
        TaskTypeFilter,
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
    list_filter = (StageTypeFilter, "status", "created_at")
    search_fields = ("task__device__hostname", "task__celery_task_id", "error_message")
    autocomplete_fields = ("task",)
    list_select_related = ("task",)
    date_hierarchy = "created_at"
