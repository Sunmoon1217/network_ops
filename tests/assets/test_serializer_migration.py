"""序列化器迁移对比测试。

对比 `assets/api/serializers.py`（旧）与 `assets/serializers/views.py`（改造版），
确保改造过程没有丢字段。旧文件删除后，本测试可一并删除。
"""

import importlib

import pytest

from assets.serializers.base import DeviceRelatedSerializer, ParentClass, model

OLD_MODULE = "assets.api.serializers"
NEW_MODULE = "assets.serializers.views"


def _pairs():
    """产出 (类名, 旧类, 新类) 三元组"""
    old = importlib.import_module(OLD_MODULE)
    new = importlib.import_module(NEW_MODULE)
    for name in sorted(dir(old)):
        if not name.endswith("Serializer"):
            continue
        old_cls = getattr(old, name, None)
        if not isinstance(old_cls, type):
            continue
        yield name, old_cls, getattr(new, name, None)


def test_new_module_covers_every_serializer():
    """新版必须包含旧版的每一个序列化器"""
    missing = [name for name, _, new_cls in _pairs() if new_cls is None]
    assert not missing, f"新版缺少序列化器: {missing}"


def test_new_model_fields_are_superset():
    """新版的模型字段必须是旧版的超集（只增不减）"""
    problems = []
    for name, old_cls, new_cls in _pairs():
        if new_cls is None:
            continue
        model_fields = {f.name for f in new_cls.Meta.model._meta.fields}
        old_exposed = set(old_cls().fields) & model_fields
        new_exposed = set(new_cls().fields) & model_fields
        missing = sorted(old_exposed - new_exposed)
        if missing:
            problems.append(f"{name} 缺少模型字段: {missing}")
    assert not problems, "\n".join(problems)


def test_decorator_completes_model_fields():
    """装饰器注入 fields="__all__" 后，旧版遗漏的模型字段应被补全"""
    from assets.models import LtmVirtualServer
    from assets.serializers.views import LtmVirtualServerSerializer

    fields = set(LtmVirtualServerSerializer().fields)
    model_fields = {f.name for f in LtmVirtualServer._meta.fields}

    assert model_fields <= fields
    # 旧版三处遗漏，改造后由 __all__ 自动补全
    assert {"status", "source", "snat_pool"} <= fields


def test_wrong_base_class_is_rejected():
    """模型没有 device 字段却继承 DeviceRelatedSerializer 时，应在类定义阶段报错"""
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
    from assets.models import LtmPool

    with pytest.raises(TypeError, match="必须是 Django 模型类"):

        @model(model=LtmPool())
        class _BadSerializer(ParentClass):
            pass
