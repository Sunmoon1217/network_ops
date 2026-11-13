"""软资产刷新信号（T4）的契约测试：提交后执行、同批合并、失败不抛出、入库链路接入。"""

import pytest

from assets.models import Device, DomainAsset, GtmPool, GtmServer, GtmVServer, GtmWideip
from assets.signals import request_soft_asset_sync


def _gtm(hostname: str, fqdn: str) -> None:
    device = Device.objects.create(hostname=hostname, device_type="gslb")
    server = GtmServer.objects.create(device=device, name="srv1")
    GtmVServer.objects.create(server=server, device=device, name="vs1", ip_address="10.0.0.1", port="80")
    GtmPool.objects.create(device=device, name="pool_web", ttl=30, members=[{"server": "srv1", "vserver": "vs1"}])
    GtmWideip.objects.create(device=device, name=fqdn, rtype="A", lb_mode="round-robin", pools=["pool_web"])


@pytest.mark.django_db
def test_request_sync_runs_after_commit(django_capture_on_commit_callbacks):
    """归并必须等事务提交：提交前读到的是配置写入的中间态"""
    _gtm("gtm-a", "a.example.com")

    with django_capture_on_commit_callbacks(execute=True):
        request_soft_asset_sync("test")

    assert DomainAsset.objects.filter(fqdn="a.example.com").exists()


@pytest.mark.django_db
def test_requests_in_one_transaction_are_coalesced(django_capture_on_commit_callbacks, monkeypatch):
    """一个事务里多台设备各请求一次，只跑最后一次全量归并"""
    from assets.services import soft_asset_sync as service

    calls: list[int] = []

    def _fake_sync(*args, **kwargs):
        calls.append(1)
        return service.SyncStats()

    monkeypatch.setattr(service, "sync_soft_assets", _fake_sync)

    with django_capture_on_commit_callbacks(execute=True):
        request_soft_asset_sync("设备 1")
        request_soft_asset_sync("设备 2")
        request_soft_asset_sync("设备 3")

    assert len(calls) == 1


@pytest.mark.django_db
def test_sync_failure_does_not_propagate(django_capture_on_commit_callbacks, monkeypatch):
    """派生资产刷新失败只记日志：配置入库已经成功，不能因此回滚或让任务失败"""
    from assets.services import soft_asset_sync as service

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "sync_soft_assets", _boom)

    with django_capture_on_commit_callbacks(execute=True):
        request_soft_asset_sync("test")  # 不应抛出


@pytest.mark.django_db
def test_device_config_pipeline_requests_sync(monkeypatch):
    """同步解析入库（DeviceConfig post_save）完成后请求刷新"""
    from assets.models import DeviceConfig
    from ingest.pipeline import PipelineResult, SaverOutcome

    calls: list[str] = []
    monkeypatch.setattr("assets.signals.request_soft_asset_sync", lambda reason="": calls.append(reason))
    monkeypatch.setattr(
        "ingest.pipeline.run_config_pipeline",
        lambda *args, **kwargs: PipelineResult(outcomes=[SaverOutcome(keys=["vlans"], created=1)]),
    )

    device = Device.objects.create(hostname="sw-1", device_type="switch")
    DeviceConfig.objects.create(device=device, git_commit_hash="a" * 40, config_json={"vlans": []})

    assert calls == ["DeviceConfig 同步解析入库"]


@pytest.mark.django_db
def test_device_config_without_saver_outcomes_does_not_request_sync(monkeypatch):
    """没跑到任何 Saver（无解析器 / 堆叠备机）时不触发全量归并"""
    from assets.models import DeviceConfig
    from ingest.pipeline import PipelineResult

    calls: list[str] = []
    monkeypatch.setattr("assets.signals.request_soft_asset_sync", lambda reason="": calls.append(reason))
    monkeypatch.setattr("ingest.pipeline.run_config_pipeline", lambda *args, **kwargs: PipelineResult(skipped="无匹配解析器"))

    device = Device.objects.create(hostname="sw-2", device_type="switch")
    DeviceConfig.objects.create(device=device, git_commit_hash="b" * 40, config_json={})

    assert calls == []
