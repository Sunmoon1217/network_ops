"""core 的任务词汇注册表：业务域在 ``ready()`` 里登记，core 只按 key 反查。

这组用例守的是「core 零业务词汇」这条分层约束里最容易被悄悄破坏的一环——
有人图省事在 core 里再写一次 ``"collection"``，注册表就形同虚设。
"""

import pytest

from core import task_types
from core.models import Stage, Task


def test_ingest_registers_vocabulary_at_startup():
    """Django 启动后（ingest 的 ready() 已跑过），三个阶段与任务类型都在表里。"""
    for stage_type in ("collection", "parsing", "storage"):
        assert callable(task_types.handler_for(stage_type).delay), f"{stage_type} 的 handler 不是 celery 任务"

    assert task_types.first_stage_of("collect_config") == "collection"
    assert task_types.is_registered_task_type("batch_collect")

    # 导入配置：单阶段（解析 → 入库），只能由导入投递，不给用户手工建
    assert task_types.first_stage_of("import_config") == "config_pipeline"
    assert callable(task_types.handler_for("config_pipeline").delay)
    assert not task_types.is_creatable_task_type("import_config")
    assert task_types.is_creatable_task_type("collect_config")


def test_labels_come_from_registry():
    assert task_types.label_for("collection") == "数据采集"
    assert task_types.label_for("collect_config") == "采集配置"


def test_unknown_label_falls_back_to_key():
    """未知词汇的 display 回落原字符串：前端看得见 key，比抛异常有用。"""
    assert task_types.label_for("no_such_type") == "no_such_type"


@pytest.mark.parametrize("func", [task_types.first_stage_of, task_types.handler_for])
def test_unknown_type_is_loud(func):
    """未注册的类型必须显式失败——静默返回空会让任务建了却不推进。"""
    with pytest.raises(LookupError, match="未知的"):
        func("no_such_type")


#: 步骤 2 之前写在模型 ``choices`` 里的词。字段现在改自由字符串了，
#: 但历史词汇与显示名必须仍由注册表兜住——老数据与老前端都还在用。
LEGACY_TASK_TYPES = {
    "collect_config": "采集配置",
    "backup_config": "备份配置",
    "ansible_playbook": "Ansible执行",
    "batch_collect": "批量采集",
    "config_backup": "配置备份",
}
LEGACY_STAGE_TYPES = {"collection": "数据采集", "parsing": "配置解析", "storage": "数据存储"}


def test_registry_covers_historical_vocabulary():
    """模型上的 ``choices`` 摘掉后，注册表是这些词的唯一出处——一个都不能漏。"""
    for key, label in LEGACY_TASK_TYPES.items():
        assert task_types.is_registered_task_type(key)
        assert task_types.label_for(key) == label
    for key, label in LEGACY_STAGE_TYPES.items():
        assert task_types.label_for(key) == label
        assert callable(task_types.handler_for(key).delay)


@pytest.mark.parametrize(("model", "field"), [(Task, "task_type"), (Stage, "stage_type")])
def test_model_fields_declare_no_business_vocabulary(model, field):
    """字段上不许再有 ``choices``：它会被写进迁移，与运行时注册永远对不上。"""
    assert not model._meta.get_field(field).choices


def test_display_methods_read_the_registry():
    """``__str__`` / admin / 序列化器都靠这两个方法；未登记的旧词回落 key 而不是报错。"""
    assert Task(task_type="collect_config").get_task_type_display() == "采集配置"
    assert Stage(stage_type="collection").get_stage_type_display() == "数据采集"
    assert Task(task_type="legacy_word").get_task_type_display() == "legacy_word"
    assert Stage(stage_type="legacy_stage").get_stage_type_display() == "legacy_stage"


@pytest.mark.django_db
def test_admin_filters_read_the_registry():
    """去 ``choices`` 之后 admin 的过滤项由注册表提供（否则会退化成按库里散值过滤）。"""
    from django.contrib.admin.sites import site
    from django.test import RequestFactory

    from core.admin import StageTypeFilter, TaskTypeFilter

    Task.objects.create(task_type="collect_config")
    Task.objects.create(task_type="backup_config")
    task_admin = site._registry[Task]

    # 过滤器的 params 形状与 request.GET 一致：值是**列表**（Django 取 value[-1]）
    params = {"task_type": ["collect_config"], "stage_type": ["parsing"]}
    request = RequestFactory().get("/admin/core/task/", params)

    task_filter = TaskTypeFilter(request, dict(params), Task, task_admin)
    assert ("collect_config", "采集配置") in task_filter.lookups(request, task_admin)
    assert list(task_filter.queryset(request, Task.objects.all())) == [Task.objects.get(task_type="collect_config")]

    stage_admin = site._registry[Stage]
    stage_filter = StageTypeFilter(request, dict(params), Stage, stage_admin)
    assert ("parsing", "配置解析") in stage_filter.lookups(request, stage_admin)


def test_assets_registers_device_target():
    """「设备」这个作用目标由 assets 在 ``ready()`` 里登记——core 自己不认识这个词。"""
    assert task_types.device_field_target_type() == "device"
    assert task_types.target_label_for("device") == "设备"
    assert ("device", "设备") in task_types.target_type_choices()


@pytest.mark.django_db
def test_device_target_resolves_hostname():
    """软引用靠 resolver 补回外键的校验能力：目标不存在必须返回 None（而不是空串）。"""
    from assets.models import Device

    device = Device.objects.create(hostname="_t_target_dev", device_type="switch")

    assert task_types.resolve_target_label("device", device.pk) == "_t_target_dev"
    assert task_types.resolve_target_label("device", device.pk + 999) is None
    assert task_types.resolve_target_label("no_such_type", device.pk) is None


def test_register_stage_rejects_non_celery_handler():
    """handler 没有 ``.delay()`` 就是接错对象了（比如传了普通函数），当场报错。"""
    with pytest.raises(TypeError, match="celery"):
        task_types.register_stage("_t_stage", "测试阶段", object())
