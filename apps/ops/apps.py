from django.apps import AppConfig


class OperatorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ops"
    label = "operator"
    verbose_name = "运维操作"

    def ready(self):
        # 导入 Saver 包会执行各模块里的类定义，__init_subclass__ 借此把 Saver 注册进
        # registry。原先只靠 signals 里那行 `from ops.savers.registry import ...` 顺带
        # 触发父包导入，一旦那行被挪进函数体（惰性导入），所有 Saver 会静默失效。
        import ops.savers  # noqa: F401
        import ops.signals  # noqa: F401
