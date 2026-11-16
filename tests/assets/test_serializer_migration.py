"""序列化器合并后的对账：旧模块已删除，公共能力与字段口径都还在。

原测试逐字段对比 `assets/api/serializers.py`（旧）与 `assets/serializers/views.py`（新）；
旧模块删除后对账对象没了，改锁三件仍然重要的契约：

1. 旧模块确实删掉（防止有人为了兼容又把它加回来）；
2. 从旧模块并入的两个展示函数还在 assets 侧（analysis 接口在用）；
3. `model` 装饰器仍按「fields=__all__」补全字段，且拒绝非法 model 参数。
"""

import importlib.util
from types import SimpleNamespace

import pytest

from assets.serializers.base import DeviceRelatedSerializer, ParentClass, model
from assets.serializers.views import _format_address_entry, _format_service_entry
from configs.serializers.views import LtmVirtualServerSerializer


def test_old_serializer_module_removed():
    """旧模块彻底删除——两套同名序列化器并存最容易漏改引用。"""
    assert importlib.util.find_spec("assets.api.serializers") is None


def test_format_helpers_survive_merge():
    """两个展示串函数并入后行为不变（analysis/api/firewall_groups.py 依赖）。"""
    address = _format_address_entry(
        SimpleNamespace(
            address_type="subnet",
            ip_start=None,
            ip_end=None,
            ip_address="10.0.0.0",
            ip_netmask=24,
            name="办公网段",
        )
    )
    service = _format_service_entry(SimpleNamespace(protocol="tcp", port="443", port2="", name="https"))
    assert address == "办公网段(10.0.0.0/24)"
    assert service == "tcp/443"


def test_decorator_completes_model_fields():
    """装饰器注入 fields="__all__" 后，旧版遗漏的模型字段应被补全。"""
    fields = set(LtmVirtualServerSerializer().fields)
    model_fields = {f.name for f in LtmVirtualServerSerializer.Meta.model._meta.fields}
    assert model_fields <= fields
    assert {"status", "source", "snat_pool"} <= fields


def test_wrong_base_class_is_rejected():
    """模型没有 device 字段却继承 DeviceRelatedSerializer 时，应在类定义阶段报错。"""
    from assets.models import Tag

    assert not hasattr(Tag, "device")

    with pytest.raises(TypeError, match="没有 device 字段"):

        @model(model=Tag)
        class _BadSerializer(DeviceRelatedSerializer):
            pass


@pytest.mark.parametrize("bad_model", ["LtmPool", dict, 123, None])
def test_model_argument_must_be_django_model(bad_model):
    """model 参数必须是 Django 模型类（拦住字符串、普通类等）"""
    with pytest.raises(TypeError, match="必须是 Django 模型类"):

        @model(model=bad_model)
        class _BadSerializer(ParentClass):
            pass


def test_model_argument_rejects_instance():
    """传模型实例同样要被拒绝"""
    from configs.models import LtmPool

    with pytest.raises(TypeError, match="必须是 Django 模型类"):

        @model(model=LtmPool())
        class _BadSerializer(ParentClass):
            pass
