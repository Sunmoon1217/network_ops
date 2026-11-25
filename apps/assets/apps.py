from django.apps import AppConfig


def resolve_device_label(device_id: int) -> str | None:
    """把设备主键解析成 hostname；设备不存在返回 ``None``。

    由 core 的任务词汇注册表调用（``Task`` 用 ``target_type`` / ``target_id`` 软引用
    设备，core 自己不查 assets 的表）。
    """
    from assets.models import Device

    return Device.objects.filter(pk=device_id).values_list("hostname", flat=True).first()


class AssetsConfig(AppConfig):
    name = "assets"
    verbose_name = "资产管理"

    def ready(self):
        # 软资产刷新信号在 configs.signals（assets 不认识 configs），本域不注册接收器
        self._register_task_target()

    def _register_task_target(self):
        """把「设备」登记成任务的作用目标类型。

        ``feeds_device_fields=True``：Task 的历史字段 device / device_hostname 由本类型填。
        """
        from core.tasktypes import register_target_type

        register_target_type("device", "设备", resolve_device_label, feeds_device_fields=True)
