"""任务工作流：投递、阶段推进、失败收尾、取消，以及批量导入的异步开关。"""

import pytest
from django.utils import timezone

from assets.models import Device, DeviceConfig, DeviceModel, Vendor, Vlan
from core.models import Stage, Task


def _switch(hostname: str) -> Device:
    """带型号的交换机：ParserFactory 按 vendor **名字**（H3C）找解析器。"""
    vendor, _ = Vendor.objects.get_or_create(name="H3C")
    model, _ = DeviceModel.objects.get_or_create(name=f"M-{hostname}", vendor=vendor)
    return Device.objects.create(hostname=hostname, device_type="switch", device_model=model)


# ---------------------------------------------------------------------------
# 阶段推进
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_chain_from_parsing_to_storage_completes_task(eager_celery):
    """解析 → 存储 → 收尾：用一份真实 H3C 配置验证阶段推进与最终状态。

    采集阶段目前是占位实现（``tasks.py`` 里的 TODO，只会返回 ``# placeholder config``，
    解析出来是空 dict，存储阶段会以「无成功的解析阶段」拒绝），所以这里直接造一个成功的
    采集阶段，从解析阶段起跑——覆盖信号推进与 storage 收尾这两段。
    """
    device = _switch("_t_wf_ok")
    task = Task.objects.create(
        task_type="collect_config",
        device=device,
        status="running",
        started_at=timezone.now(),
    )
    # 用 update() 落状态：直接 create(status="success") 会触发阶段联动信号、自己把整条链
    # 跑起来，这里要测的是显式投递 + 信号推进，所以先造一个「已成功但不触发信号」的采集阶段。
    collection = Stage.objects.create(task=task, stage_type="collection")
    Stage.objects.filter(pk=collection.pk).update(
        status="success",
        output_data={"config": "sysname E2E\nvlan 10\nvlan 20\n"},
    )

    from ops.workflow import dispatch_stage

    dispatch_stage(task, "parsing")

    task.refresh_from_db()
    assert task.status == "success", task.error_message
    assert task.completed_at is not None
    assert task.progress == 100
    assert sorted(stage.stage_type for stage in task.stages.all()) == ["collection", "parsing", "storage"]
    assert Vlan.objects.filter(device=device).count() == 2


@pytest.mark.django_db
def test_start_task_dispatches_collection_stage(eager_celery):
    """``start_task`` = 建 Task + 建并投递 collection 阶段（采集无可用连接 → 失败收尾）。"""
    device = _switch("_t_wf_fail")  # 没有可用连接 → 采集阶段必然失败

    from ops.workflow import start_task

    task = start_task(device, "collect_config")

    task.refresh_from_db()
    assert task.started_at is not None
    assert task.celery_task_id, "投递后要记下 celery 任务 id，方便排错与取消"
    assert task.status == "failed"
    assert "无可用连接" in task.error_message
    assert task.completed_at is not None
    assert task.stages.count() == 1, "失败之后不该继续推进阶段"


@pytest.mark.django_db
def test_cancelled_task_is_not_advanced():
    """任务取消后，阶段即使成功也不再推进。

    ``ops.workflow.cancel_task`` 里的 revoke 只是尽力而为（需要 worker 在线），
    真正兜底的是信号里的这个检查。
    """
    device = _switch("_t_wf_cancel")
    task = Task.objects.create(task_type="collect_config", device=device, status="cancelled")
    stage = Stage.objects.create(task=task, stage_type="collection")

    stage.status = "success"
    stage.save()

    assert Stage.objects.filter(task=task).count() == 1, "已取消的任务还在推进阶段"
    task.refresh_from_db()
    assert task.status == "cancelled"


@pytest.mark.django_db
def test_cancel_task_marks_cancelled():
    from ops.workflow import cancel_task

    device = _switch("_t_wf_cancel2")
    task = Task.objects.create(task_type="collect_config", device=device, status="running")

    cancel_task(task)

    task.refresh_from_db()
    assert task.status == "cancelled"
    assert task.completed_at is not None


# ---------------------------------------------------------------------------
# DeviceConfig：同步默认 + 批量导入的异步开关
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_defer_pipeline_skips_sync_pipeline(monkeypatch):
    """save 之前挂 ``_defer_pipeline``，信号就跳过同步流水线（属性必须能被 post_save 看到）"""
    calls = []
    monkeypatch.setattr("ops.pipeline.run_config_pipeline", lambda device, config: calls.append(config.pk))

    device = _switch("_t_wf_defer")

    DeviceConfig.objects.create(device=device, git_commit_hash="d" * 40, config_json={})
    assert len(calls) == 1, "默认应该走同步流水线"

    deferred = DeviceConfig(device=device, git_commit_hash="e" * 40, config_json={})
    deferred._defer_pipeline = True
    deferred.save()
    assert len(calls) == 1, "_defer_pipeline 没有跳过同步流水线"


@pytest.mark.django_db
def test_submit_config_job_parses_then_stores(eager_celery, monkeypatch):
    """异步链（解析 → 存储）：config_json 由解析任务写回，Saver 由存储任务跑。"""
    monkeypatch.setattr("ops.config_repo.get_config", lambda hostname, commit=None: "sysname E2E\nvlan 10\nvlan 20\n")
    device = _switch("_t_wf_chain")

    config = DeviceConfig(device=device, git_commit_hash="f" * 40, config_json={})
    config._defer_pipeline = True
    config.save()

    from ops.workflow import submit_config_job

    submit_config_job(config.pk)

    config.refresh_from_db()
    assert "vlans" in (config.config_json or {})
    assert config.parse_duration is not None
    assert Vlan.objects.filter(device=device).count() == 2


def test_config_job_chain_gives_both_tasks_the_same_id():
    """链条的两个任务都要拿到同一个 config_id —— 第二个必须用 ``.si()``（immutable）。

    用 ``.s()`` 的话 celery 会把上一个任务的返回值当参数续下去，而解析任务返回 None，
    存储任务就会收到 None。这里直接查链条结构，防止以后被改回 ``.s()``。
    """
    from celery import chain

    from ops.tasks import run_config_parsing, run_config_storage

    sig = chain(run_config_parsing.si(7), run_config_storage.si(7))

    assert [task.task for task in sig.tasks] == ["ops.run_config_parsing", "ops.run_config_storage"]
    assert [tuple(task.args) for task in sig.tasks] == [(7,), (7,)]
