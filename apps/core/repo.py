"""Git 配置仓库管理：每台设备一个独立仓库 ``<CONFIG_REPO_PATH>/<hostname>/``。

仓库里只入库 ``running-config.txt``。独立仓库让 HEAD 永远是本设备的上次提交，
``configs`` 表按 ``(device, hash)`` 去重才不会被别的设备污染；首次打开时会把旧共享仓库
里该设备的历史重放进来。背景与迁移见 handbook/deploy.md，归 core 的原因见 layering.md。

core 不认识 ``DeviceConfig``：重放后的新老 hash 通过 ``register_hash_remapper()`` 钩子
交给 configs 回写（由 configs 在 ``ready()`` 注册）。
"""

import logging
from collections.abc import Callable
from pathlib import Path

import git
import git.exc
import gitdb.exc
from django.conf import settings

logger = logging.getLogger(__name__)

REPO_FILE = "running-config.txt"  # 设备仓库内的配置文件名（仓库根 = 设备目录）


def repo_root() -> Path:
    """仓库根目录。每次调用都读 ``settings.CONFIG_REPO_PATH``（测试用 override_settings 换目录）。"""
    return Path(settings.CONFIG_REPO_PATH)


def _device_dir(hostname: str) -> Path:
    """设备目录 = ``<CONFIG_REPO_PATH>/<hostname>``；拒绝会越出仓库根的设备名。"""
    name = hostname.strip()
    if not name or name in {".", ".."} or name.startswith((".", "/")) or "/" in name or "\\" in name:
        raise ValueError(f"非法设备名: {hostname!r}")
    return repo_root() / name


def _write_gitignore(repo_dir: Path) -> None:
    (repo_dir / ".gitignore").write_text("# Config repo\n*.tmp\n*.bak\n")


def _legacy_repo() -> git.Repo | None:
    """旧的共享仓库根（只读兜底；不存在返回 None，**不主动创建**）。"""
    root = repo_root()
    if not (root / ".git").exists():
        return None
    try:
        return git.Repo(str(root))
    except (git.exc.InvalidGitRepositoryError, git.exc.NoSuchPathError):
        return None


def _tree_text(tree: git.Tree, hostname: str) -> str | None:
    """从提交树取配置原文：先找设备仓库的 ``REPO_FILE``，再找旧共享仓库的 ``<hostname>/...``。"""
    for fp in (REPO_FILE, f"{hostname}/{REPO_FILE}"):
        try:
            return tree[fp].data_stream.read().decode("utf-8")
        except KeyError:
            continue
    return None


def init_repo(hostname: str | None = None) -> git.Repo:
    """打开配置仓库。

    给 ``hostname`` 返回该设备的独立仓库（不存在则初始化并重放旧共享仓库历史）；
    不传参数返回旧的共享仓库根，仅留给兼容调用方。
    """
    if hostname is None:
        root = repo_root()
        root.mkdir(parents=True, exist_ok=True)
        if not (root / ".git").exists():
            repo = git.Repo.init(str(root))
            _write_gitignore(root)
            repo.index.add([".gitignore"])
            repo.index.commit("init: 初始化配置仓库")
        return git.Repo(str(root))

    device_dir = _device_dir(hostname)
    device_dir.mkdir(parents=True, exist_ok=True)
    if not (device_dir / ".git").exists():
        repo = git.Repo.init(str(device_dir))
        _write_gitignore(device_dir)
        repo.index.add([".gitignore"])
        repo.index.commit("init: 初始化配置仓库")
        try:
            _adopt_legacy_history(repo, hostname)
        except Exception:  # 迁移是尽力而为：失败不挡读写，旧 hash 由读取路径兜底
            logger.exception("重放共享仓库历史失败 hostname=%s", hostname)
    return git.Repo(str(device_dir))


def _adopt_legacy_history(device_repo: git.Repo, hostname: str) -> None:
    """首次打开设备仓库时，把旧共享仓库里该设备的历史逐个版本重放进新仓库并通知回写 hash。

    父链不同 ⇒ hash 必然改变，指向旧 hash 的记录必须回写。
    """
    legacy = _legacy_repo()
    if legacy is None:
        return
    legacy_fp = f"{hostname}/{REPO_FILE}"
    try:
        commits = list(legacy.iter_commits(rev="HEAD", paths=legacy_fp))
    except Exception as e:  # 旧仓库损坏 / 尚无提交
        logger.warning("读取共享仓库历史失败 hostname=%s: %s", hostname, e)
        return
    if not commits:
        return

    config_file = _device_dir(hostname) / REPO_FILE
    mapping: dict[str, str] = {}  # 旧 hash → 新 hash
    for c in reversed(commits):  # 从旧到新重放，链才线性
        try:
            data = c.tree[legacy_fp].data_stream.read()
        except KeyError:
            continue
        config_file.write_bytes(data)
        device_repo.index.add([REPO_FILE])
        new = device_repo.index.commit(
            message=c.message if isinstance(c.message, str) else c.message.decode("utf-8", errors="replace"),
            author=c.author,
            committer=c.committer,
            author_date=c.authored_datetime,
            commit_date=c.committed_datetime,
        )
        mapping[c.hexsha] = new.hexsha
    if not mapping:
        return
    logger.info("已重放共享仓库历史 hostname=%s：%d 个提交", hostname, len(mapping))
    _notify_hash_remappers(hostname, mapping)


#: 「重放旧历史后回写 hash」的钩子签名：(hostname, {旧 hash: 新 hash}) -> None。
#: core 不认识 ``DeviceConfig``——那张表归 configs，钩子由 configs 在 ``ready()`` 里注册。
HashRemapper = Callable[[str, dict[str, str]], None]
_HASH_REMAPPERS: list[HashRemapper] = []


def register_hash_remapper(remapper: HashRemapper) -> None:
    """注册 hash 回写钩子（幂等：同一个函数重复注册只保留一份）。"""
    if remapper not in _HASH_REMAPPERS:
        _HASH_REMAPPERS.append(remapper)


def legacy_commit_for(hostname: str, commit_hash: str) -> str | None:
    """旧共享仓库里「≤ 该 hash 时点、真正改过本设备文件」的提交 hash（查不到返回 None）。

    给回写钩子用：历史 bug 留下过指向其它设备 commit 的脏行，需用此锚点换算重放后的版本。
    """
    legacy = _legacy_repo()
    if legacy is None:
        return None
    try:
        anchor = next(legacy.iter_commits(rev=commit_hash, paths=f"{hostname}/{REPO_FILE}", max_count=1))
    except (StopIteration, git.exc.GitCommandError, gitdb.exc.BadName, ValueError):
        return None  # 假 hash（测试数据等）：调用方保持原样
    return anchor.hexsha


def _notify_hash_remappers(hostname: str, mapping: dict[str, str]) -> None:
    """重放完成 → 通知各域把自家表里指向旧 hash 的记录改指新 hash。

    回调失败只记日志：迁移是尽力而为，读不到的旧 hash 由 ``get_config`` 的共享仓库兜底。
    """
    for remapper in list(_HASH_REMAPPERS):
        try:
            remapper(hostname, mapping)
        except Exception:
            logger.exception("hash 回写钩子失败 %s hostname=%s（旧 hash 由读取兜底）", getattr(remapper, "__module__", remapper), hostname)


def save_config(hostname: str, config_text: str, message: str = "") -> str:
    repo = init_repo(hostname)
    config_file = _device_dir(hostname) / REPO_FILE

    try:
        old = repo.head.commit.tree[REPO_FILE].data_stream.read().decode("utf-8")
        if old == config_text:
            # 内容没变：返回本设备自己的上一次提交，configs 表去重天然命中
            return repo.head.commit.hexsha
    except (KeyError, git.exc.GitCommandError, gitdb.exc.BadName, ValueError, TypeError):
        pass

    config_file.write_text(config_text, encoding="utf-8")
    repo.index.add([REPO_FILE])
    commit = repo.index.commit(message or f"update: {hostname} config")
    return commit.hexsha


def get_config(hostname: str, commit_hash: str | None = None) -> str | None:
    try:
        repo = init_repo(hostname)
    except ValueError:
        return None
    try:
        tree = repo.commit(commit_hash).tree if commit_hash else repo.head.commit.tree
        text = _tree_text(tree, hostname)
        if text is not None:
            return text
    except (git.exc.GitCommandError, gitdb.exc.BadName, gitdb.exc.BadObject, ValueError, TypeError):
        pass

    # 兜底读旧共享仓库：覆盖迁移窗口（调用方手里还是旧 hash）与回写失败的脏行
    legacy = _legacy_repo()
    if legacy is None:
        return None
    try:
        c = legacy.commit(commit_hash) if commit_hash else legacy.head.commit
        return _tree_text(c.tree, hostname)
    except (git.exc.GitCommandError, gitdb.exc.BadName, gitdb.exc.BadObject, ValueError, TypeError):
        return None


def _resolve_commit(hostname: str, commit_hash: str | None) -> git.Commit | None:
    """按 hash 定位提交：先设备仓库，再回退共享仓库（旧 hash）；不传 hash 取设备 HEAD。"""
    try:
        device_repo = init_repo(hostname)
    except ValueError:
        return None
    if not commit_hash:
        try:
            return device_repo.head.commit
        except (ValueError, git.exc.GitCommandError, gitdb.exc.BadName):
            return None
    for repo in (device_repo, _legacy_repo()):
        if repo is None:
            continue
        try:
            return repo.commit(commit_hash)
        except (git.exc.GitCommandError, gitdb.exc.BadName, gitdb.exc.BadObject, ValueError, TypeError):
            continue
    return None


def diff_configs(hostname: str, old_hash: str | None = None, new_hash: str | None = None) -> str | None:
    import difflib

    new_c = _resolve_commit(hostname, new_hash)
    if new_c is None:
        return None
    try:
        new_text = _tree_text(new_c.tree, hostname)
        if new_text is None:
            return None
        if old_hash:
            old_c = _resolve_commit(hostname, old_hash)
        else:
            old_c = new_c.parents[0] if new_c.parents else None
        if old_c is None:
            return None
        old_text = _tree_text(old_c.tree, hostname)
        if old_text is None:
            return f"+ {new_text}"
        diff = difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"old/{hostname}/{REPO_FILE}",
            tofile=f"new/{hostname}/{REPO_FILE}",
        )
        return "".join(diff) or None
    except (KeyError, git.exc.GitCommandError) as e:
        logger.error("配置对比失败: %s", e)
        return None


def get_history(hostname: str, limit: int = 20) -> list[dict]:
    try:
        repo = init_repo(hostname)
    except ValueError:
        return []
    try:
        commits = list(repo.iter_commits(paths=REPO_FILE, max_count=limit))
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
    """列出仓库中所有设备（扫目录：含 ``running-config.txt`` 的设备目录）。"""
    base = repo_root()
    if not base.exists():
        return []
    devices = []
    for item in base.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            if (item / REPO_FILE).exists():
                devices.append(item.name)
    return sorted(devices)
