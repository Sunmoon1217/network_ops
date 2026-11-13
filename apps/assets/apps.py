from django.apps import AppConfig


class AssetsConfig(AppConfig):
    name = "assets"
    verbose_name = "资产管理"

    def ready(self):
        # 注册软资产刷新信号（配置入库后自动归并，T4）
        import assets.signals  # noqa: F401
