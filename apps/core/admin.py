from django.contrib import admin

from . import tasktypes
from .models import IntegrationHealth, Stage, Task, Token, User, UserPreference

admin.site.site_header = "网络运维管理平台"
admin.site.site_title = "网络运维管理平台"
admin.site.index_title = "后台管理"


class VocabularyListFilter(admin.SimpleListFilter):
    """按 ``core.tasktypes`` 注册表快照出过滤项（字段已无 ``choices``，直接写字段会退化）。"""

    def vocabulary(self) -> list[tuple[str, str]]:
        """子类返回 ``[(值, 显示名)]``，通常是某个 ``*_choices()`` 快照。"""
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
        return tasktypes.task_type_choices()


class StageTypeFilter(VocabularyListFilter):
    title = "阶段类型"
    parameter_name = "stage_type"

    def vocabulary(self):
        return tasktypes.stage_type_choices()


class TargetTypeFilter(VocabularyListFilter):
    title = "作用目标类型"
    parameter_name = "target_type"

    def vocabulary(self):
        return tasktypes.target_type_choices()


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
        "target",
        "celery_task_id",
        "created_at",
        "started_at",
        "completed_at",
    )
    list_filter = (
        TaskTypeFilter,
        TargetTypeFilter,
        "status",
        "created_at",
    )
    # 作用目标是软引用，名字在 target_label 里（建任务时记下），不需要 join 业务表
    search_fields = ("target_label", "celery_task_id", "error_message")
    date_hierarchy = "created_at"
    inlines = (StageInline,)

    @admin.display(description="作用目标")
    def target(self, obj):
        """列表里的作用目标：``名字（type#id）``，无目标显示破折号。"""
        if not obj.target_id:
            return "—"
        return f"{obj.target_label or '?'}（{obj.target_type}#{obj.target_id}）"


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
    search_fields = ("task__target_label", "task__celery_task_id", "error_message")
    autocomplete_fields = ("task",)
    list_select_related = ("task",)
    date_hierarchy = "created_at"


@admin.register(IntegrationHealth)
class IntegrationHealthAdmin(admin.ModelAdmin):
    """探活结果的只读视图：写入只走 ``core.integrations.probe_all``（beat 周期任务）。"""

    list_display = ("system", "instance", "status", "checked_at")
    list_filter = ("status", "system")
    search_fields = ("system", "instance", "error")
    readonly_fields = ("system", "instance", "status", "checked_at", "error")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
