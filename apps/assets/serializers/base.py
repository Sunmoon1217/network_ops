"""序列化器公共基类与 ``@model`` 装饰器。

用法与两个基类的分工见 handbook/assets.md「序列化器」。
"""

from django.db import models as django_models
from rest_framework import serializers


def model(*, model):
    """类装饰器：为该 ModelSerializer 子类注入 ``Meta``（``fields="__all__"``、仅主键只读）。

    子类自定义 ``Meta`` 时完全尊重；模型有 device 字段校验：``hasattr(model, "device")``，
    不要求继承 ``ConfigBase``。
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
