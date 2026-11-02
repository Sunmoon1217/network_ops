from django.apps import AppConfig


class SheetsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sheets"
    verbose_name = "通用表格（xlsx 编辑与历史）"
