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


def test_model_choices_agree_with_registry():
    """对账：模型 ``choices`` 与注册表是同一套词与同一套显示名。

    步骤 2 会把 ``choices`` 从模型上摘掉，那时这条断言改成「注册表覆盖历史词汇」即可；
    在此之前它防的是「注册表里换了词，前端 display 跟着变但迁移没动」这种漂移。
    """
    for key, label in Task.TASK_TYPES:
        assert task_types.label_for(key) == label
    for key, label in Stage.STAGE_TYPES:
        assert task_types.label_for(key) == label


def test_register_stage_rejects_non_celery_handler():
    """handler 没有 ``.delay()`` 就是接错对象了（比如传了普通函数），当场报错。"""
    with pytest.raises(TypeError, match="celery"):
        task_types.register_stage("_t_stage", "测试阶段", object())
