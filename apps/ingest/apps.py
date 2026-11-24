from django.apps import AppConfig


class OperatorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ingest"  # 2026-09 由 ingest 改名：作用域是「数据采集与解析入库」（采、解、存三段）
    # label 是**迁移历史的主键**（django_migrations.app 全是 'operator'），改它会让已有库的
    # 迁移记录对不上——目录与 name 可以改，label 永远不动。类名 OperatorConfig 同理保留。
    label = "operator"
    verbose_name = "数据摄入（采集与解析入库）"

    def ready(self):
        # Saver 注册点已随 Registry 迁到 configs.apps（本域不再负责触发）
        import ingest.signals  # noqa: F401

        self._register_integrations()
        self._register_task_vocabulary()

    def _register_integrations(self):
        """把本域用到的外部系统 provider 登记进 core（方向：域 → core）。

        Zabbix 的 client 单例住在 ``core/integrations/providers/zabbix/``，但「本项目用不用
        Zabbix、用哪个实例」是采集域的决定，所以注册动作在这里——core 只提供注册表，
        自己不 import 任何具体系统（``tests/core/test_layering.py`` 守着这条）。
        """
        from core.integrations import register_provider
        from core.integrations.providers.zabbix import ZabbixProvider

        register_provider(ZabbixProvider())

    def _register_task_vocabulary(self):
        """把 ingest 的任务类型 / 阶段词汇登记进 core 注册表（方向：域 → core）。

        core 只按 key 反查，见 ``handbook/tasks.md``。
        """
        from core.task_types import register_stage, register_task_type
        from ingest.tasks import run_collection_stage, run_config_pipeline_stage, run_parsing_stage, run_storage_stage

        # 五个任务类型当前都从采集阶段起跑（与拆分前 start_task 的硬编码行为一致）
        for task_type, label in (
            ("collect_config", "采集配置"),
            ("backup_config", "备份配置"),
            ("ansible_playbook", "Ansible执行"),
            ("batch_collect", "批量采集"),
            ("config_backup", "配置备份"),
        ):
            register_task_type(task_type, label, first_stage="collection")

        # 导入配置：单阶段（解析 → 入库），由 Excel 导入自己投递，不给用户手工建
        register_task_type("import_config", "导入配置", first_stage="config_pipeline", creatable=False)

        register_stage("collection", "数据采集", run_collection_stage)
        register_stage("parsing", "配置解析", run_parsing_stage)
        register_stage("storage", "数据存储", run_storage_stage)
        register_stage("config_pipeline", "配置解析入库", run_config_pipeline_stage)
