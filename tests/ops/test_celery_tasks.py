"""Celery 阶段任务的失败传播回归测试。

守护一条约束：阶段任务失败时，**数据库里的 Stage 与 Celery 的任务状态必须一致**。
历史缺陷：``apps/ops/tasks.py`` 三个阶段任务的 except 只写 ``_update_stage_status``
而漏了 ``raise``，导致 Stage=failed 但 ``task.state`` 仍是 SUCCESS，
AsyncResult / Flower 的失败告警与重试全部失效。
"""

import pytest

from core.models import Stage, Task
from ops.tasks import run_collection_stage, run_parsing_stage, run_storage_stage

# eager_celery 是共享 fixture，见 tests/conftest.py


@pytest.mark.django_db
def test_collection_failure_marks_task_as_failure(eager_celery):
    """设备无可用连接 → 采集阶段失败，Celery 状态必须是 FAILURE。"""
    from assets.models import Device

    device = Device.objects.create(hostname="celery-fail-no-conn", device_type="switch")
    task = Task.objects.create(task_type="collect_config", device=device)
    stage = Stage.objects.create(task=task, stage_type="collection")

    result = run_collection_stage.delay(stage.pk)

    stage.refresh_from_db()
    assert stage.status == "failed"
    assert stage.error_message
    assert result.state == "FAILURE", "阶段失败必须向上抛，否则 Celery 会记成 SUCCESS"


@pytest.mark.django_db
def test_parsing_failure_marks_task_as_failure(eager_celery):
    """无成功的采集阶段 → 解析阶段失败，Celery 状态必须是 FAILURE。"""
    from assets.models import Device

    device = Device.objects.create(hostname="celery-fail-no-collection", device_type="switch")
    task = Task.objects.create(task_type="collect_config", device=device)
    stage = Stage.objects.create(task=task, stage_type="parsing")

    result = run_parsing_stage.delay(stage.pk)

    stage.refresh_from_db()
    assert stage.status == "failed"
    assert result.state == "FAILURE", "阶段失败必须向上抛，否则 Celery 会记成 SUCCESS"


# ---------------------------------------------------------------------------
# 存储阶段：Saver 的 key 是**列表**
# ---------------------------------------------------------------------------


def _stage_with_parsed_data(task, parsed_data) -> Stage:
    """造一个「已成功的解析阶段」。

    用 ``.update()`` 而不是 ``create(status="success")``：后者会触发
    ``on_stage_complete`` 信号、自动把 storage 阶段也跑起来，测试就重复执行了。
    """
    parsing = Stage.objects.create(task=task, stage_type="parsing")
    Stage.objects.filter(pk=parsing.pk).update(status="success", output_data=parsed_data)
    return parsing


@pytest.mark.django_db
def test_storage_stage_writes_every_matched_saver(eager_celery):
    """存储阶段要把解析结果按 key 分组喂给各 Saver。

    历史缺陷：``run_storage_stage`` 把 ``get_savers_for_config`` 返回的第一个元素
    （**key 列表**）当成单个 key 用，``parsed_data.get(["interfaces"])`` 抛
    ``TypeError: unhashable type: 'list'``，凡是匹配到 Saver 的设备都存不进去。
    """
    from assets.models import Device, Interface, Vlan

    device = Device.objects.create(hostname="celery-store-ok", device_type="switch")
    task = Task.objects.create(task_type="collect_config", device=device)
    _stage_with_parsed_data(
        task,
        {
            "interfaces": [{"interface": "GE0/1", "mode": "access"}],
            "vlans": [{"vlan_id": "10"}],
        },
    )
    storage = Stage.objects.create(task=task, stage_type="storage")

    run_storage_stage.delay(storage.pk)

    storage.refresh_from_db()
    assert storage.status == "success", storage.error_message
    assert storage.output_data["created"] == 2
    assert Interface.objects.filter(device=device).count() == 1
    assert Vlan.objects.filter(device=device, vid=10).count() == 1


@pytest.mark.django_db
def test_storage_failure_marks_task_as_failure(eager_celery, monkeypatch):
    """存储阶段失败时 Stage=failed 且 Celery 状态为 FAILURE（与采集/解析一致）"""
    from assets.models import Device
    from ops.savers.interface import InterfaceSaver

    def _boom(self, device, parsed_data):
        raise RuntimeError("模拟 Saver 故障")

    monkeypatch.setattr(InterfaceSaver, "save", _boom)

    device = Device.objects.create(hostname="celery-store-fail", device_type="switch")
    task = Task.objects.create(task_type="collect_config", device=device)
    _stage_with_parsed_data(task, {"interfaces": [{"interface": "GE0/1"}]})
    storage = Stage.objects.create(task=task, stage_type="storage")

    result = run_storage_stage.delay(storage.pk)

    storage.refresh_from_db()
    assert storage.status == "failed"
    assert "模拟 Saver 故障" in storage.error_message
    assert result.state == "FAILURE", "阶段失败必须向上抛，否则 Celery 会记成 SUCCESS"


def test_multi_key_saver_receives_all_matched_keys():
    """命中同一个 Saver 的多个 key 必须一起传。

    PolicySaver 注册了 policies / acl / rules 三个 key，内部是
    ``a or b or c`` 的短路链——只传第一个的话其余 key 的数据会被静默丢弃。
    """
    from ops.savers.firewall import PolicySaver
    from ops.savers.registry import build_saver_payloads

    payloads = build_saver_payloads(
        "firewall",
        {"policies": [{"policy_id": "1"}], "rules": [{"rule_id": "2"}]},
    )

    assert len(payloads) == 1, "同一个 Saver 的多个 key 不该拆成多次调用"
    saver, payload = payloads[0]
    assert isinstance(saver, PolicySaver)
    assert sorted(payload) == ["policies", "rules"]


def test_each_saver_only_receives_its_own_keys():
    """每个 Saver 只能看到自己注册的 key。

    ``run_config_storage`` 原先把整个 config_json 递给每个 Saver，等于让它们
    看到不属于自己的键——注册的 key 写错了也测不出来。
    """
    from ops.savers.registry import all_savers, build_saver_payloads

    config = {"interfaces": [1], "vlans": [1], "vpn_instances": [1], "policies": [1], "rules": [1]}
    registry_map = all_savers()

    checked = 0
    for device_type in ("switch", "firewall"):
        for saver, payload in build_saver_payloads(device_type, config):
            own = {key for (dt, key), cls in registry_map.items() if dt == device_type and cls is type(saver)}
            assert set(payload) <= own, f"{type(saver).__name__} 拿到了不属于它的键 {set(payload) - own}"
            checked += 1

    assert checked, "这个用例没匹配到任何 Saver，等于没测"
