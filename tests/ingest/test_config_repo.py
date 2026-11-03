"""每设备独立配置仓库（``config_repo.init_repo(hostname)``）的行为。

覆盖四件事：

1. 仓库隔离：每台设备一个 ``.git``，链上只有自己的文件——内容未变时返回的必然是
   **自己**的上一次提交（回归：共享线性链时代会返回别人的 commit，configs 表误判新版本）。
2. 首次打开自动迁移：旧共享仓库里该设备的历史逐条重放（message / 作者 / 时间保留），
   configs 表的 ``git_commit_hash`` 回写成重放后的新 hash。
3. 历史 bug 产生的脏行（指向其它设备 commit）按「≤该时点改过本设备文件的提交」锚点回写。
4. 读取兜底：迁移没跑到的旧 hash 仍能通过共享仓库读到（get_config / diff）。
"""

from datetime import datetime, timezone
from pathlib import Path

import git
import pytest

from assets.models import Device, DeviceConfig, DeviceModel, Vendor
from ingest import config_repo


@pytest.fixture(autouse=True)
def _repo_path(tmp_path, monkeypatch):
    """把仓库根挪进 tmp：绝不碰真实的 data/config_repo。"""
    root = tmp_path / "config_repo"
    monkeypatch.setattr(config_repo, "CONFIG_REPO_PATH", root)
    return root


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch):
    monkeypatch.setenv("GIT_AUTHOR_NAME", "test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.com")


@pytest.fixture
def device(db):
    vendor = Vendor.objects.create(name="V-repo")
    model = DeviceModel.objects.create(name="M-repo", vendor=vendor)
    return Device.objects.create(hostname="dev-a", device_type="switch", device_model=model)


def _legacy_root(root: Path, hostname: str, versions: list[tuple[str, str, datetime]]) -> git.Repo:
    """造一个旧的共享仓库：init 提交 + 该设备的若干版本（旧→新）。"""
    root.mkdir(parents=True, exist_ok=True)
    repo = git.Repo.init(str(root))
    (root / ".gitignore").write_text("# Config repo\n*.tmp\n*.bak\n")
    repo.index.add([".gitignore"])
    repo.index.commit("init: 初始化配置仓库")
    for message, content, when in versions:
        device_dir = root / hostname
        device_dir.mkdir(exist_ok=True)
        (device_dir / "running-config.txt").write_text(content, encoding="utf-8")
        repo.index.add([f"{hostname}/running-config.txt"])
        repo.index.commit(message, author_date=when, commit_date=when)
    return repo


def test_isolated_repos_and_unchanged_config_returns_own_commit(_repo_path):
    a = config_repo.save_config("dev-a", "sysname A\n", "import: dev-a config")
    b = config_repo.save_config("dev-b", "sysname B\n", "import: dev-b config")
    assert (_repo_path / "dev-a" / ".git").is_dir()
    assert (_repo_path / "dev-b" / ".git").is_dir()

    # 核心回归：dev-a 内容没变，即使 dev-b 刚提交过，返回的必须是 dev-a 自己的提交
    again = config_repo.save_config("dev-a", "sysname A\n", "import: dev-a config")
    assert again == a
    assert again != b

    repo_a = git.Repo(str(_repo_path / "dev-a"))
    messages = [c.message.splitlines()[0] for c in repo_a.iter_commits()]
    assert messages == ["import: dev-a config", "init: 初始化配置仓库"]
    assert config_repo.get_config("dev-a", a) == "sysname A\n"
    assert config_repo.get_config("dev-b", b) == "sysname B\n"


def test_history_lists_only_this_device_versions(_repo_path):
    config_repo.save_config("dev-a", "one\n", "v1")
    config_repo.save_config("dev-b", "other\n", "dev-b v1")
    config_repo.save_config("dev-a", "two\n", "v2")

    history = config_repo.get_history("dev-a")
    assert [h["message"] for h in history] == ["v2", "v1"]
    assert config_repo.get_history("dev-b")[0]["message"] == "dev-b v1"

    diff = config_repo.diff_configs("dev-a", history[1]["full_hash"], history[0]["full_hash"])
    assert "-one" in diff and "+two" in diff


@pytest.mark.django_db
def test_first_open_replays_legacy_history_and_rewrites_hashes(_repo_path, device):
    when1 = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    when2 = datetime(2026, 2, 3, 4, 5, 6, tzinfo=timezone.utc)
    legacy = _legacy_root(_repo_path, "dev-a", [("v1: 基线", "one\n", when1), ("v2: 改ACL", "two\n", when2)])
    old_tip = next(legacy.iter_commits()).hexsha  # 共享链头（v2）
    old_v1 = list(legacy.iter_commits())[1].hexsha
    cfg = DeviceConfig.objects.create(device=device, git_commit_hash=old_tip, config_json={"x": 1})

    history = config_repo.get_history("dev-a")  # 首次打开 → 自动迁移

    assert [h["message"] for h in history] == ["v2: 改ACL", "v1: 基线"]
    assert history[0]["date"].startswith("2026-02-03T04:05:06"), "重放要保留原提交时间"
    new_tip, new_v1 = history[0]["full_hash"], history[1]["full_hash"]
    assert new_tip != old_tip, "父链变了 hash 必然不同，所以才要回写"

    cfg.refresh_from_db()
    assert cfg.git_commit_hash == new_tip
    assert config_repo.get_config("dev-a", new_tip) == "two\n"
    assert config_repo.get_config("dev-a", new_v1) == "one\n"
    assert config_repo.get_config("dev-a", old_v1) == "one\n", "未回写引用的旧 hash 由共享仓库兜底"

    # 内容没变的重复导入直接命中回写后的 hash → 不再新增记录
    assert config_repo.save_config("dev-a", "two\n", "import: dev-a config") == new_tip


@pytest.mark.django_db
def test_dirty_row_pointing_at_foreign_commit_is_anchored(_repo_path, device):
    """历史 bug 留下的脏行（指向其它设备的 commit）要锚到本设备的对应版本。"""
    when = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    legacy = _legacy_root(_repo_path, "dev-a", [("v1: 基线", "one\n", when)])
    dev_b_dir = _repo_path / "dev-b"
    dev_b_dir.mkdir(parents=True, exist_ok=True)
    (dev_b_dir / "running-config.txt").write_text("b\n", encoding="utf-8")
    legacy.index.add(["dev-b/running-config.txt"])
    foreign = legacy.index.commit("import: dev-b config", author_date=when, commit_date=when).hexsha

    dirty = DeviceConfig.objects.create(device=device, git_commit_hash=foreign, config_json={})

    history = config_repo.get_history("dev-a")
    dirty.refresh_from_db()
    assert dirty.git_commit_hash != foreign, "不该继续指向 dev-b 的提交"
    assert dirty.git_commit_hash == history[0]["full_hash"], "应锚到本设备 v1 重放后的提交"


def test_get_config_and_diff_fall_back_to_legacy_repo(_repo_path):
    """迁移没跑到（先有设备仓库、后出现共享仓库）时，旧 hash 仍可读、可 diff。"""
    config_repo.init_repo("dev-a")  # 此时还没有共享仓库 → 不迁移

    when = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    legacy = _legacy_root(_repo_path, "dev-a", [("v1", "old content\n", when)])
    old_hash = next(legacy.iter_commits()).hexsha

    assert config_repo.get_config("dev-a", old_hash) == "old content\n"
    assert config_repo.get_history("dev-a") == [], "迁移没跑就不该凭空出现重放的历史"

    new_hash = config_repo.save_config("dev-a", "new content\n")
    diff = config_repo.diff_configs("dev-a", old_hash, new_hash)
    assert "-old content" in diff and "+new content" in diff
