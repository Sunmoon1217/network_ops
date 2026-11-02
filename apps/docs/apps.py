from django.apps import AppConfig


class DocsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "docs"
    verbose_name = "文档（表格编辑与文档转换）"
