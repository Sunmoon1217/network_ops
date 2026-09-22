from django.apps import AppConfig


class AnalysisConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "analysis"
    verbose_name = "分析（路径追踪 / 资产分析）"

    # 本 app 没有需要注册的信号：Saver 注册表在 ops.apps.OperatorConfig.ready() 里，
    # 拆分时保持那里的 `import ops.savers` 不动（见 apps/ops/apps.py 注释）。
