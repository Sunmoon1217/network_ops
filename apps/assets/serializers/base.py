"""序列化器公共基类与装饰器。

用法::

    @model(model=LtmPool)
    class LtmPoolSerializer(DeviceRelatedSerializer):
        pass

两个基类的区别：

- ``ParentClass``：模型没有 device 外键
- ``DeviceRelatedSerializer``：模型有 device 外键，统一提供 ``device_hostname`` 展示字段

装饰器只负责注入 ``Meta``（``fields="__all__"``、仅主键只读）；
时间戳等 ``editable=False`` 字段由 DRF 自动置为只读，无需逐一声明。
"""

from django.db import models as django_models
from rest_framework import serializers


def model(*, model):
    """类装饰器：为该 ModelSerializer 子类注入 Meta。

    - 统一 ``fields="__all__"``、``read_only_fields=("id",)``
    - 子类若自己定义了 ``Meta``（例如列表页需要精简字段），完全尊重子类
    - 附带一致性校验：模型没有 device 字段却继承了 ``DeviceRelatedSerializer`` 时
      直接报错。否则 ``source="device.hostname"`` 会静默返回空串（因为字段带 default），
      属于难以察觉的错误

    这里校验「是否为 Django 模型类」，而**不**要求模型继承 ``ConfigBase``：
    序列化器覆盖全部资产（设备 / DCIM / IPAM / 拓扑 / 地址表），其中 23 个模型并不
    继承 ``ConfigBase``；判断是否带 device 也应以 ``hasattr(model, "device")`` 为准
    （``Vlan`` / ``ArpMac`` 等有 device 字段但不继承 ConfigBase）。
    """
    if not (isinstance(model, type) and issubclass(model, django_models.Model)):
        raise TypeError(f"model 参数必须是 Django 模型类，收到 {model!r}")

    def decorator(cls):
        # 用 cls.__dict__ 判断，而不是 hasattr：否则会误把父类继承来的 Meta 当成子类自己的
        if "Meta" not in cls.__dict__:
            cls.Meta = type("Meta", (), {"model": model, "fields": "__all__", "read_only_fields": ("id",)})

        if getattr(cls, "requires_model_device", False) and not hasattr(model, "device"):
            raise TypeError(f"{cls.__name__}: 模型 {model.__name__} 没有 device 字段，不能继承 DeviceRelatedSerializer")
        return cls

    return decorator


class ParentClass(serializers.ModelSerializer):
    """无 device 外键的模型基类（抽象，不要直接实例化）"""

    # 子类若继承 DeviceRelatedSerializer，用该标记触发模型匹配性校验
    requires_model_device = False


class DeviceRelatedSerializer(ParentClass):
    """带 device 外键的模型基类：统一提供 device_hostname 展示字段"""

    requires_model_device = True
    device_hostname = serializers.CharField(source="device.hostname", read_only=True, default="")
