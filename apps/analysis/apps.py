from django.apps import AppConfig


class AnalysisConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "analysis"
    verbose_name = "分析（路径追踪 / 资产分析）"

    # 本 app 无信号可注册；Saver 注册在 configs.apps.ConfigsConfig.ready()
