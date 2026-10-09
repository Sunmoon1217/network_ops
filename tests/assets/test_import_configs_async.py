"""Excel 导入配置：批量导入改成投递 celery 链。

原先 `_import_configs` 每行 `get_or_create(DeviceConfig)` 都会触发同步流水线，
几十行配置就在**一个 HTTP 请求**里串行跑几十次「解析 + 全部 Saver 入库」
（实测单台 0.2–12 s）。现在挂 `_defer_pipeline` 让信号跳过同步处理，改投递
`ingest.workflow.submit_config_job`（解析 → 存储）。
"""

import pytest
from openpyxl import Workbook

from assets.models import Device, DeviceConfig, DeviceModel, Vendor


@pytest.fixture
def device(db):
    vendor = Vendor.objects.create(name="V-imp")
    model = DeviceModel.objects.create(name="M-imp", vendor=vendor)
    return Device.objects.create(hostname="_t_imp_dev", device_type="switch", device_model=model)


def _sheet(rows):
    ws = Workbook().active
    ws.append(["主机名", "文件名", "配置目录"])
    for row in rows:
        ws.append(row)
    return ws


@pytest.mark.django_db
def test_import_dispatches_async_and_skips_sync(device, tmp_path, monkeypatch):
    cfg = tmp_path / "_t_imp_dev.txt"
    cfg.write_text("sysname IMP\nvlan 10\n", encoding="utf-8")

    sync_calls = []
    monkeypatch.setattr("ingest.pipeline.run_config_pipeline", lambda dev, config: sync_calls.append(config.pk))
    monkeypatch.setattr("assets.device_import.save_config", lambda hostname, text, message="": "a" * 40)

    submitted = []
    monkeypatch.setattr("ingest.workflow.submit_config_job", lambda pk: submitted.append(pk))

    from assets.device_import import _import_configs

    result = _import_configs(_sheet([["_t_imp_dev", cfg.name, str(tmp_path)]]))

    assert result["created"] == 1 and not result["errors"], result
    assert not sync_calls, "批量导入不该在请求里跑同步流水线"
    assert len(submitted) == 1

    config = DeviceConfig.objects.get()
    assert config.device_id == device.pk
    assert config.config_json == {}, "异步路径下 config_json 由 celery 任务填写"
    assert submitted[0] == config.pk


@pytest.mark.django_db
def test_import_skips_existing_commit_and_does_not_dispatch_again(device, tmp_path, monkeypatch):
    cfg = tmp_path / "_t_imp_dev.txt"
    cfg.write_text("sysname IMP\nvlan 10\n", encoding="utf-8")

    monkeypatch.setattr("assets.device_import.save_config", lambda hostname, text, message="": "b" * 40)
    submitted = []
    monkeypatch.setattr("ingest.workflow.submit_config_job", lambda pk: submitted.append(pk))

    from assets.device_import import _import_configs

    first = _import_configs(_sheet([["_t_imp_dev", cfg.name, str(tmp_path)]]))
    second = _import_configs(_sheet([["_t_imp_dev", cfg.name, str(tmp_path)]]))

    assert first["created"] == 1
    assert second["created"] == 0 and second["skipped"] == 1, second
    assert DeviceConfig.objects.count() == 1
    assert len(submitted) == 1, "重复导入同一 commit 不该再投递解析任务"


@pytest.mark.django_db
def test_import_reports_dispatch_failure_per_row(device, tmp_path, monkeypatch):
    """投递失败（broker 不可达）要出现在该行的 errors 里，而不是静默丢掉"""
    cfg = tmp_path / "_t_imp_dev.txt"
    cfg.write_text("sysname IMP\n", encoding="utf-8")

    monkeypatch.setattr("assets.device_import.save_config", lambda hostname, text, message="": "c" * 40)

    def _boom(pk):
        raise RuntimeError("broker down")

    monkeypatch.setattr("ingest.workflow.submit_config_job", _boom)

    from assets.device_import import _import_configs

    result = _import_configs(_sheet([["_t_imp_dev", cfg.name, str(tmp_path)]]))

    assert result["created"] == 1
    assert any("投递解析任务失败" in err and "broker down" in err for err in result["errors"]), result


@pytest.mark.django_db
def test_import_unchanged_config_skipped_across_devices(tmp_path, monkeypatch):
    """回归（走真实 save_config 的端到端）：两台设备**交替**导入时，内容未变的设备不该新增记录。

    共享线性链时代的故障形态：dev-a 内容没变，但 HEAD 已经被 dev-b 的提交顶掉，
    ``save_config`` 早退返回的是 dev-b 的 commit → configs 表按 (device, hash) 去重失效，
    dev-a 每轮都多一条重复记录并重跑一次解析。
    """
    monkeypatch.setattr("ingest.config_repo.CONFIG_REPO_PATH", tmp_path / "repo")
    for key, value in (
        ("GIT_AUTHOR_NAME", "test"),
        ("GIT_AUTHOR_EMAIL", "test@example.com"),
        ("GIT_COMMITTER_NAME", "test"),
        ("GIT_COMMITTER_EMAIL", "test@example.com"),
    ):
        monkeypatch.setenv(key, value)

    submitted = []
    monkeypatch.setattr("ingest.workflow.submit_config_job", lambda pk: submitted.append(pk))

    vendor = Vendor.objects.create(name="V-2dev")
    model = DeviceModel.objects.create(name="M-2dev", vendor=vendor)
    Device.objects.create(hostname="_t_imp_a", device_type="switch", device_model=model)
    Device.objects.create(hostname="_t_imp_b", device_type="switch", device_model=model)

    src = tmp_path / "src"
    src.mkdir()
    (src / "_t_imp_a.txt").write_text("sysname A\nvlan 10\n", encoding="utf-8")
    (src / "_t_imp_b.txt").write_text("sysname B\n", encoding="utf-8")

    from assets.device_import import _import_configs

    def _pair():
        ws = Workbook().active
        ws.append(["主机名", "文件名", "配置目录"])
        ws.append(["_t_imp_a", "_t_imp_a.txt", str(src)])
        ws.append(["_t_imp_b", "_t_imp_b.txt", str(src)])
        return ws

    first = _import_configs(_pair())
    second = _import_configs(_pair())

    assert first["created"] == 2 and not first["errors"], first
    assert second["created"] == 0 and second["skipped"] == 2, second
    assert DeviceConfig.objects.count() == 2, "内容未变的两台设备都不该新增记录"
    assert len(submitted) == 2, "不该重复投递解析任务"
