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

        self._register_task_vocabulary()

    def _register_task_vocabulary(self):
        """把 ingest 的任务类型 / 阶段词汇登记进 core 的注册表。

        方向是「业务域 → core」：core 不认识这些词，只在建任务、投递阶段、渲染
        ``*_display`` 时按 key 反查（见 ``handbook/tasks.md``）。
        词汇原先硬编码在模型字段的 ``choices`` 里；``choices`` 会写进迁移、运行时追加
        必然造成迁移漂移，所以现在由这里登记词与显示名，模型字段是自由字符串。
        """
        from core.task_types import register_stage, register_task_type
        from ingest.tasks import run_collection_stage, run_parsing_stage, run_storage_stage

        # 五个任务类型当前都从采集阶段起跑（与拆分前 start_task 的硬编码行为一致）
        for task_type, label in (
            ("collect_config", "采集配置"),
            ("backup_config", "备份配置"),
            ("ansible_playbook", "Ansible执行"),
            ("batch_collect", "批量采集"),
            ("config_backup", "配置备份"),
        ):
            register_task_type(task_type, label, first_stage="collection")

        register_stage("collection", "数据采集", run_collection_stage)
        register_stage("parsing", "配置解析", run_parsing_stage)
        register_stage("storage", "数据存储", run_storage_stage)
