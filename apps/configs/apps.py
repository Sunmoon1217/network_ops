from django.apps import AppConfig


class ConfigsConfig(AppConfig):
    """配置域。

    ``label`` 必须与 ``name`` 一致（都是 ``configs``）：迁移历史按它记账，与 assets 拆开后
    两者必须是不同 label。表名随之从 ``assets_*`` 变成 ``configs_*``（迁移用 RENAME），
    见 handbook/design/assets-configs.md「迁移手法」。
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "configs"
    verbose_name = "设备配置"

    def ready(self):
        # 导入 Saver 包触发类定义，__init_subclass__ 借此完成注册
        import configs.savers  # noqa: F401

        # 软资产刷新信号的语义是「配置行变了」，所以住在配置域
        import configs.signals  # noqa: F401
        from configs.repo_hashes import remap_device_config_hashes

        # core 不认识 DeviceConfig，重放旧历史后的 hash 回写由本域注册钩子
        from core.repo import register_hash_remapper

        register_hash_remapper(remap_device_config_hashes)
