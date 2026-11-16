from django.apps import AppConfig


class ConfigsConfig(AppConfig):
    """配置域。

    ``label`` 必须与 ``name`` 一致（都是 ``configs``）：它是迁移历史的主键，
    与 assets 拆开之后两者必须是不同的 label，否则 Django 报 ``ImproperlyConfigured``。
    表名因此从 ``assets_*`` 变成 ``configs_*``，迁移用 RENAME 而不是重建
    （见 ``handbook/design/assets-configs-split.md`` §迁移手法）。
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "configs"
    verbose_name = "设备配置"

    def ready(self):
        # 导入 Saver 包会执行各模块里的类定义，__init_subclass__ 借此把 Saver 注册进
        # registry。Saver 已随解析/写入链路迁入本域，注册点也跟着搬过来——原先放在
        # ingest.apps 里会形成 ingest → configs 之外的隐式启动顺序依赖。
        import configs.savers  # noqa: F401

        # 软资产刷新信号的接收器：语义是「配置行变了」，所以住在配置域
        # （拆分前在 assets.signals，会让 assets 认识 configs，方向被矩阵禁止）。
        import configs.signals  # noqa: F401
        from configs.repo_hashes import remap_device_config_hashes

        # 配置仓库重放旧历史后要把 DeviceConfig.git_commit_hash 改指新 hash。core 不认识
        # 这张表，所以由本域注册钩子（core 只提供钩子点与旧仓库锚点查询）。
        from core.config_repo import register_hash_remapper

        register_hash_remapper(remap_device_config_hashes)
