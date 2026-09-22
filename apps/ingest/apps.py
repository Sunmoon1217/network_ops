from django.apps import AppConfig


class OperatorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ingest"  # 2026-09 由 ingest 改名：作用域是「数据采集与解析入库」（采、解、存三段）
    # label 是**迁移历史的主键**（django_migrations.app 全是 'operator'），改它会让已有库的
    # 迁移记录对不上——目录与 name 可以改，label 永远不动。类名 OperatorConfig 同理保留。
    label = "operator"
    verbose_name = "数据摄入（采集与解析入库）"

    def ready(self):
        # 导入 Saver 包会执行各模块里的类定义，__init_subclass__ 借此把 Saver 注册进
        # registry。原先只靠 signals 里那行 `from ingest.savers.registry import ...` 顺带
        # 触发父包导入，一旦那行被挪进函数体（惰性导入），所有 Saver 会静默失效。
        import ingest.savers  # noqa: F401
        import ingest.signals  # noqa: F401
