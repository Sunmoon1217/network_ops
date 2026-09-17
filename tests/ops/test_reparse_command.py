"""reparse 管理命令测试。

正常流程只在 DeviceConfig 新建时触发解析入库，重复导入同一 commit 是空操作，
所以重跑需要显式入口。这里覆盖重新解析、沿用 config_json、跳过原因与错误退出码。

用 monkeypatch 替换 config_repo.get_config，避免测试往真实的 data/config_repo
里写配置文件。
"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from assets.models import Device, DeviceConfig, DeviceModel, Interface, Vendor, Vlan

CONFIG = "sysname E2E-SW\nvlan 10\nvlan 20\ninterface GigabitEthernet1/0/1\n port access vlan 10\n"


@pytest.fixture
def h3c_model(db):
    vendor = Vendor.objects.create(name="H3C")
    return DeviceModel.objects.create(name="S5560X", vendor=vendor)


def _make_config(hostname: str, model, config_json: dict | None = None) -> DeviceConfig:
    device = Device.objects.create(hostname=hostname, device_type="switch", device_model=model)
    return DeviceConfig.objects.create(device=device, git_commit_hash="abc1234", config_json=config_json or {})


def _run(*args) -> str:
    out = StringIO()
    call_command("reparse", *args, stdout=out, stderr=StringIO())
    return out.getvalue()


@pytest.mark.django_db
def test_reparse_parses_and_runs_savers(monkeypatch, h3c_model):
    """--device 会重新解析并跑 Saver"""
    monkeypatch.setattr("ops.config_repo.get_config", lambda hostname, commit=None: CONFIG)
    config = _make_config("rp-sw-01", h3c_model)

    output = _run("--device", "rp-sw-01")

    assert "已重新解析" in output
    assert "vlans" in output and "interfaces" in output
    config.refresh_from_db()
    assert "vlans" in config.config_json
    assert Vlan.objects.filter(device=config.device).count() == 2
    assert Interface.objects.filter(device=config.device).count() == 1


@pytest.mark.django_db
def test_reparse_no_parse_reuses_existing_config_json(monkeypatch, h3c_model):
    """--no-parse 不读 Git，直接用已有 config_json 跑 Saver"""

    def _boom(hostname, commit=None):
        raise AssertionError("--no-parse 不应读取 Git")

    monkeypatch.setattr("ops.config_repo.get_config", _boom)
    config = _make_config("rp-sw-02", h3c_model, config_json={"vlans": [{"vlan_id": "30"}]})

    output = _run("--device", "rp-sw-02", "--no-parse")

    assert "沿用 config_json" in output
    assert Vlan.objects.filter(device=config.device).count() == 1


@pytest.mark.django_db
def test_reparse_reports_skip_reason(monkeypatch, h3c_model):
    """Git 里没有配置时，应该报告跳过原因而不是静默什么都不做"""
    monkeypatch.setattr("ops.config_repo.get_config", lambda hostname, commit=None: None)
    _make_config("rp-sw-03", h3c_model)

    output = _run("--device", "rp-sw-03")

    assert "跳过" in output
    assert "Git 无配置" in output


@pytest.mark.django_db
def test_reparse_without_device_model_reports_skip(monkeypatch, h3c_model):
    """设备没设型号时，解析器匹配失败应作为跳过原因报出来（而不是抛 AttributeError）"""
    monkeypatch.setattr("ops.config_repo.get_config", lambda hostname, commit=None: CONFIG)
    device = Device.objects.create(hostname="rp-sw-04", device_type="switch")
    DeviceConfig.objects.create(device=device, git_commit_hash="abc1234", config_json={})

    output = _run("--device", "rp-sw-04")

    assert "跳过" in output
    assert "未设置型号" in output


@pytest.mark.django_db
def test_reparse_unknown_device_raises(h3c_model):
    with pytest.raises(CommandError, match="设备不存在"):
        _run("--device", "不存在的设备")


@pytest.mark.django_db
def test_reparse_device_without_config_raises(h3c_model):
    Device.objects.create(hostname="rp-sw-05", device_type="switch", device_model=h3c_model)

    with pytest.raises(CommandError, match="没有 DeviceConfig 记录"):
        _run("--device", "rp-sw-05")


@pytest.mark.django_db
def test_reparse_all_takes_latest_config_per_device(monkeypatch, h3c_model):
    """--all 每台设备只处理最新一条，不重跑历史版本"""
    monkeypatch.setattr("ops.config_repo.get_config", lambda hostname, commit=None: CONFIG)
    device = Device.objects.create(hostname="rp-sw-06", device_type="switch", device_model=h3c_model)
    DeviceConfig.objects.create(device=device, git_commit_hash="old0001", config_json={})
    latest = DeviceConfig.objects.create(device=device, git_commit_hash="new0002", config_json={})

    output = _run("--all", "--no-parse")

    # 只有最新那条参与（沿用已有 config_json，所以不会去读 Git）
    assert "rp-sw-06" in output
    assert latest.pk == DeviceConfig.objects.filter(device=device).order_by("-pk").first().pk


@pytest.mark.django_db
def test_reparse_saver_failure_raises_command_error(monkeypatch, h3c_model):
    """单个 Saver 失败时应以非零退出码收尾，方便脚本判断"""
    monkeypatch.setattr("ops.config_repo.get_config", lambda hostname, commit=None: CONFIG)
    _make_config("rp-sw-07", h3c_model)

    from ops.savers import registry

    def _boom(self, device, parsed_data):
        raise RuntimeError("模拟 Saver 故障")

    original = registry.get_savers_for_config

    def _patched(device_type, config_json):
        savers = original(device_type, config_json)
        for _, saver in savers:
            saver.save = _boom.__get__(saver, type(saver))
        return savers

    monkeypatch.setattr("ops.savers.registry.get_savers_for_config", _patched)

    with pytest.raises(CommandError, match="Saver 执行失败"):
        _run("--device", "rp-sw-07")


# ---------- 并行 / 命令内按设备分组 ----------


@pytest.mark.django_db
def test_reparse_dedupes_repeated_device(monkeypatch, h3c_model):
    """同一个 hostname 传多次只处理一次。

    不去重的话，并行时会有多个 worker 同时写同一台设备的同一批行，
    正是要避免的那种并发。
    """
    monkeypatch.setattr("ops.config_repo.get_config", lambda hostname, commit=None: CONFIG)
    _make_config("rp-dup", h3c_model)

    output = _run("--device", "rp-dup", "--device", "rp-dup")

    assert output.count("rp-dup: 已重新解析") == 1
    assert "完成：1 台设备" in output


@pytest.mark.django_db
def test_reparse_rejects_zero_workers(monkeypatch, h3c_model):
    monkeypatch.setattr("ops.config_repo.get_config", lambda hostname, commit=None: CONFIG)
    _make_config("rp-w0", h3c_model)

    with pytest.raises(CommandError, match="--workers 必须 >= 1"):
        _run("--device", "rp-w0", "--workers", "0")


@pytest.mark.django_db(transaction=True)
def test_reparse_parallel_writes_same_result_as_sequential(monkeypatch):
    """跨设备并行：每台设备各写各的，结果与顺序执行一致。

    transaction=True 是必须的：子进程连的是同一个测试库，但看不到父进程
    未提交的事务，包裹式事务下子进程会读不到这些 DeviceConfig。
    """
    monkeypatch.setattr("ops.config_repo.get_config", lambda hostname, commit=None: CONFIG)
    vendor = Vendor.objects.create(name="H3C")
    model = DeviceModel.objects.create(name="S5560X-par", vendor=vendor)
    hostnames = [f"rp-par-{i}" for i in range(4)]
    for hostname in hostnames:
        _make_config(hostname, model)

    output = _run("--all", "--workers", "4")

    assert "并行度 4" in output
    assert "完成：4 台设备，0 个 Saver 失败" in output
    for hostname in hostnames:
        device = Device.objects.get(hostname=hostname)
        assert Vlan.objects.filter(device=device).count() == 2
        assert Interface.objects.filter(device=device).count() == 1


@pytest.mark.django_db(transaction=True)
def test_reparse_parallel_reports_saver_failure(monkeypatch):
    """并行时子进程里的 Saver 失败要能回传，并以非零退出码收尾"""
    monkeypatch.setattr("ops.config_repo.get_config", lambda hostname, commit=None: CONFIG)
    vendor = Vendor.objects.create(name="H3C")
    model = DeviceModel.objects.create(name="S5560X-fail", vendor=vendor)
    _make_config("rp-par-fail-1", model)
    _make_config("rp-par-fail-2", model)

    from ops.savers import registry

    def _boom(self, device, parsed_data):
        raise RuntimeError("模拟 Saver 故障")

    original = registry.get_savers_for_config

    def _patched(device_type, config_json):
        savers = original(device_type, config_json)
        for _, saver in savers:
            saver.save = _boom.__get__(saver, type(saver))
        return savers

    monkeypatch.setattr("ops.savers.registry.get_savers_for_config", _patched)

    with pytest.raises(CommandError, match="Saver 执行失败"):
        _run("--all", "--workers", "2")
