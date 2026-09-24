"""``purge_configs`` 管理命令。

守护的语义：默认只报告不删除；``--yes`` 才删；只清「配置解析产物 + DeviceConfig +
派生缓存」，人工/Excel 数据一律不动；堆叠组的备机折算到主设备；``--purge-repo`` 必须
与 ``--all`` 同用。
"""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from analysis.models import AccessFlow, InternetAnalysis
from assets.models import (
    ConfigBase,
    Device,
    DeviceConfig,
    DeviceGroup,
    DeviceGroupMember,
    Route,
    ServerOwner,
    Vrf,
)
from core.models import Stage, Task


def _device(hostname: str) -> Device:
    return Device.objects.create(hostname=hostname, device_type="switch")


def _config_rows(device: Device) -> None:
    """造两条配置解析产物：Vrf + Route（都是 ConfigBase 子类）。"""
    vrf = Vrf.objects.create(device=device, name="default")
    Route.objects.create(vrf=vrf, device=device, destination="10.0.0.0/24", protocol="static")


def _run(*args, **kwargs) -> str:
    out = StringIO()
    call_command("purge_configs", *args, stdout=out, **kwargs)
    return out.getvalue()


# ---------------------------------------------------------------------------
# dry-run 与 --yes
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_dry_run_is_default_and_deletes_nothing():
    device = _device("_t_purge_a")
    _config_rows(device)
    DeviceConfig.objects.create(device=device, git_commit_hash="a" * 40, config_json={"x": 1})
    InternetAnalysis.objects.create(device=device, result={"x": 1}, duration_ms=1)

    output = _run("--device", device.hostname)

    assert "dry-run" in output
    assert "Route" in output and "DeviceConfig" in output
    assert Vrf.objects.count() == 1, "dry-run 不该删任何东西"
    assert Route.objects.count() == 1
    assert DeviceConfig.objects.count() == 1
    assert InternetAnalysis.objects.count() == 1


@pytest.mark.django_db
def test_yes_removes_config_products_but_keeps_manual_data():
    device = _device("_t_purge_b")
    _config_rows(device)
    DeviceConfig.objects.create(device=device, git_commit_hash="b" * 40, config_json={"x": 1})
    InternetAnalysis.objects.create(device=device, result={"x": 1}, duration_ms=1)
    ServerOwner.objects.create(hostname="_t_purge_b", ip="192.0.2.10", owner="张三")

    output = _run("--device", device.hostname, "--yes")

    assert "完成" in output
    # 配置产物 + 记录 + 缓存都清了
    assert Vrf.objects.count() == 0
    assert Route.objects.count() == 0
    assert DeviceConfig.objects.count() == 0
    assert InternetAnalysis.objects.count() == 0
    # 人工数据与设备本身不动
    assert Device.objects.filter(pk=device.pk).exists(), "设备是人工数据，不该被删"
    assert ServerOwner.objects.filter(ip="192.0.2.10").exists()


@pytest.mark.django_db
def test_covers_every_configbase_subclass():
    """命令按 ConfigBase 的子类枚举目标：抽查几个不同领域的模型都会被清掉"""
    device = _device("_t_purge_c")
    vrf = Vrf.objects.create(device=device, name="default")
    Route.objects.create(vrf=vrf, device=device, destination="10.0.0.0/24", protocol="static")
    from assets.models import AddressBook, Interface, Vlan

    Interface.objects.create(device=device, interface="GE0/1")
    Vlan.objects.create(device=device, vid=10)
    AddressBook.objects.create(device=device, name="any", address_type="host", ip_address="10.0.0.1")

    _run("--all", "--yes")

    assert ConfigBase.__subclasses__(), "枚举不到子类说明命令的定义失效了"
    for model in (Vrf, Route, Interface, Vlan, AddressBook):
        assert model.objects.count() == 0, f"{model.__name__} 没被清掉"


# ---------------------------------------------------------------------------
# 工作流记录（可选）
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_workflow_records_are_kept_unless_flagged():
    device = _device("_t_purge_d")
    task = Task.objects.create(task_type="collect_config", device=device, status="failed")
    Stage.objects.create(task=task, stage_type="collection", status="failed")

    output = _run("--device", device.hostname, "--yes")

    assert Task.objects.count() == 1 and Stage.objects.count() == 1
    assert "未清理" in output and "output_data" in output


@pytest.mark.django_db
def test_with_workflow_removes_task_and_stage():
    device = _device("_t_purge_e")
    task = Task.objects.create(task_type="collect_config", device=device, status="failed")
    Stage.objects.create(task=task, stage_type="collection", status="failed")
    Stage.objects.create(task=task, stage_type="parsing", status="success")

    _run("--device", device.hostname, "--yes", "--with-workflow")

    assert Task.objects.count() == 0
    assert Stage.objects.count() == 0


# ---------------------------------------------------------------------------
# 堆叠组：备机折算到主设备
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_stack_backup_resolves_to_master():
    master = _device("_t_purge_master")
    backup = _device("_t_purge_backup")
    group = DeviceGroup.objects.create(name="_t_purge_stack", group_type="stack")
    DeviceGroupMember.objects.create(group=group, device=master, device_role="master")
    DeviceGroupMember.objects.create(group=group, device=backup, device_role="backup")
    # 配置与产物都在主设备名下（备机不持有配置）
    _config_rows(master)
    DeviceConfig.objects.create(device=master, git_commit_hash="c" * 40, config_json={})

    output = _run("--device", backup.hostname, "--yes")

    assert "_t_purge_master" in output, "应该提示折算到了主设备"
    assert Route.objects.count() == 0
    assert Vrf.objects.count() == 0
    assert DeviceConfig.objects.count() == 0


# ---------------------------------------------------------------------------
# 访问流（AccessFlow）：跨设备聚合行按 contexts 里的设备清理
# ---------------------------------------------------------------------------


def _access_flow(device: Device, *, src_ip: str = "10.0.0.1") -> AccessFlow:
    """造一条挂着该设备上下文的访问流（AccessFlow 没有 device 字段，上下文里带着）"""
    return AccessFlow.objects.create(
        src_ip=src_ip,
        src_prefix=32,
        dst_ip="10.0.0.2",
        dst_prefix=32,
        protocol="tcp",
        port="80",
        contexts={f"{device.pk}:1": {"device_id": device.pk, "policy_pk": 1, "hostname": device.hostname}},
        device_ids=[device.pk],
        policy_ids=[1],
    )


@pytest.mark.django_db
def test_access_flow_reported_then_removed_per_device():
    target = _device("_t_purge_af")
    other = _device("_t_purge_af_other")
    mine = _access_flow(target)
    theirs = _access_flow(other, src_ip="192.0.2.1")

    output = _run("--device", target.hostname)
    assert "AccessFlow" in output, "dry-run 报告里要出现访问流"
    assert AccessFlow.objects.count() == 2, "dry-run 不删"

    _run("--device", target.hostname, "--yes")

    assert not AccessFlow.objects.filter(pk=mine.pk).exists(), "挂着目标设备的行要删"
    assert AccessFlow.objects.filter(pk=theirs.pk).exists(), "只挂着别的设备的行不能误删"


# ---------------------------------------------------------------------------
# 参数校验与 --purge-repo
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_requires_device_or_all():
    with pytest.raises(CommandError):
        _run()


@pytest.mark.django_db
def test_unknown_device_raises():
    with pytest.raises(CommandError, match="设备不存在"):
        _run("--device", "no-such-device")


@pytest.mark.django_db
def test_purge_repo_requires_all():
    device = _device("_t_purge_f")
    with pytest.raises(CommandError, match="--purge-repo"):
        _run("--device", device.hostname, "--yes", "--purge-repo")


@pytest.mark.django_db
def test_purge_repo_removes_directory(tmp_path, monkeypatch):
    repo = tmp_path / "config_repo"
    (repo / "_t_purge_g").mkdir(parents=True)
    (repo / "_t_purge_g" / "running.txt").write_text("sysname X\n", encoding="utf-8")
    monkeypatch.setattr("ingest.config_repo.CONFIG_REPO_PATH", repo)

    device = _device("_t_purge_g")
    _config_rows(device)

    output = _run("--all", "--yes", "--purge-repo")

    assert not repo.exists(), "仓库目录应该被删掉"
    assert "已删除 Git 仓库目录" in output
    assert Vrf.objects.count() == 0 and Route.objects.count() == 0


@pytest.mark.django_db
def test_repo_is_kept_without_flag(tmp_path, monkeypatch):
    repo = tmp_path / "config_repo"
    repo.mkdir()
    (repo / "keep.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr("ingest.config_repo.CONFIG_REPO_PATH", repo)

    _run("--all", "--yes")

    assert (repo / "keep.txt").exists(), "不带 --purge-repo 时不该碰文件系统"
