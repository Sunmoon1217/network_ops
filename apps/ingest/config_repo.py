"""Git 配置仓库管理"""

import logging
import os
from pathlib import Path

import git
import git.exc
import gitdb.exc

logger = logging.getLogger(__name__)

CONFIG_REPO_PATH = Path(
    os.environ.get(
        "CONFIG_REPO_PATH",
        str(Path(__file__).resolve().parents[2] / "data" / "config_repo"),
    )
)


def init_repo():
    CONFIG_REPO_PATH.mkdir(parents=True, exist_ok=True)
    if not (CONFIG_REPO_PATH / ".git").exists():
        repo = git.Repo.init(str(CONFIG_REPO_PATH))
        gi = CONFIG_REPO_PATH / ".gitignore"
        gi.write_text("# Config repo\n*.tmp\n*.bak\n")
        repo.index.add([".gitignore"])
        repo.index.commit("init: 初始化配置仓库")
    return git.Repo(str(CONFIG_REPO_PATH))


def save_config(hostname: str, config_text: str, message: str = "") -> str:
    repo = init_repo()
    device_dir = CONFIG_REPO_PATH / hostname
    device_dir.mkdir(exist_ok=True)
    config_file = device_dir / "running-config.txt"
    repo_file = str(config_file.relative_to(CONFIG_REPO_PATH))

    try:
        old = repo.head.commit.tree[repo_file].data_stream.read().decode("utf-8")
        if old == config_text:
            return repo.head.commit.hexsha
    except (KeyError, git.exc.GitCommandError):
        pass

    config_file.write_text(config_text, encoding="utf-8")
    repo.index.add([repo_file])
    commit = repo.index.commit(message or f"update: {hostname} config")
    return commit.hexsha


def get_config(hostname: str, commit_hash: str | None = None) -> str | None:
    repo = init_repo()
    fp = f"{hostname}/running-config.txt"
    try:
        blob = (repo.commit(commit_hash).tree if commit_hash else repo.head.commit.tree) / fp
        return blob.data_stream.read().decode("utf-8")
    except (KeyError, git.exc.GitCommandError, gitdb.exc.BadName):
        # BadName：commit_hash 在仓库里不存在（例如配置记录残留了已丢弃的提交）
        return None


def diff_configs(hostname: str, old_hash: str | None = None, new_hash: str | None = None) -> str | None:
    import difflib

    repo = init_repo()
    fp = f"{hostname}/running-config.txt"
    try:
        new_c = repo.commit(new_hash) if new_hash else repo.head.commit
        old_c = repo.commit(old_hash) if old_hash else (new_c.parents[0] if new_c.parents else None)
        if not old_c:
            return None
        try:
            new_text = new_c.tree[fp].data_stream.read().decode("utf-8")
        except KeyError:
            return None
        try:
            old_text = old_c.tree[fp].data_stream.read().decode("utf-8")
        except KeyError:
            return f"+ {new_text}"
        diff = difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"old/{fp}",
            tofile=f"new/{fp}",
        )
        return "".join(diff) or None
    except (KeyError, git.exc.GitCommandError) as e:
        logger.error("配置对比失败: %s - %s", hostname, e)
        return None


def get_history(hostname: str, limit: int = 20) -> list[dict]:
    repo = init_repo()
    fp = f"{hostname}/running-config.txt"
    try:
        commits = list(repo.iter_commits(paths=fp, max_count=limit))
        return [
            {
                "hash": c.hexsha[:8],
                "full_hash": c.hexsha,
                "date": c.committed_datetime.isoformat(),
                "message": c.message.strip(),
            }
            for c in commits
        ]
    except git.exc.GitCommandError:
        return []


def list_devices() -> list[str]:
    """列出仓库中所有设备"""
    init_repo()
    devices = []
    for item in CONFIG_REPO_PATH.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            if (item / "running-config.txt").exists():
                devices.append(item.name)
    return sorted(devices)
