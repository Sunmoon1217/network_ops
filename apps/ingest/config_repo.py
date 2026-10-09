"""Git 配置仓库管理

**每台设备一个独立仓库**：``CONFIG_REPO_PATH/<hostname>/``，仓库根就是该设备目录，
入库的只有 ``running-config.txt``（设备目录里放的其它源文件不入库）。

为什么不再共用一条线性链：共享链的 HEAD 属于「最后提交的那台设备」，``save_config``
在新旧内容相同时直接返回 HEAD——设备交替导入时会把**别的设备的 commit** 当结果返回，
configs 表按 ``(device, git_commit_hash)`` 去重便误判成新版本（重复记录 + 重复解析，
且该 commit 在本设备的文件历史里根本不存在）。独立仓库后每台设备的 HEAD 就是自己
最后一次提交，内容未变即返回自己的旧 hash，去重天然正确。

存量迁移（**首次打开某设备仓库时自动执行**）：若存在旧的共享仓库（``CONFIG_REPO_PATH/.git``，
只读兜底、不主动创建），把该设备在其中的历史**逐条重放**进新仓库（保留 message / 作者 /
提交时间；父链变了，hash 必然不同），随后把 configs 表 ``DeviceConfig.git_commit_hash``
指向旧 hash 的记录回写成新 hash。回写覆盖不到的旧 hash（回写失败、历史 bug 产生的脏行）
由读取路径兜底：``get_config`` / ``diff_configs`` 查不到时回退读共享仓库，不会出现「Git 无配置」。
"""

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

REPO_FILE = "running-config.txt"  # 设备仓库内的配置文件名（仓库根 = 设备目录）


def _device_dir(hostname: str) -> Path:
    """设备目录 = ``CONFIG_REPO_PATH/<hostname>``；拒绝会越出仓库根的设备名。"""
    name = hostname.strip()
    if not name or name in {".", ".."} or name.startswith((".", "/")) or "/" in name or "\\" in name:
        raise ValueError(f"非法设备名: {hostname!r}")
    return Path(CONFIG_REPO_PATH) / name


def _write_gitignore(repo_dir: Path) -> None:
    (repo_dir / ".gitignore").write_text("# Config repo\n*.tmp\n*.bak\n")


def _legacy_repo() -> git.Repo | None:
    """旧的共享仓库根（只读兜底；不存在返回 None，**不主动创建**）。"""
    if not (Path(CONFIG_REPO_PATH) / ".git").exists():
        return None
    try:
        return git.Repo(str(CONFIG_REPO_PATH))
    except (git.exc.InvalidGitRepositoryError, git.exc.NoSuchPathError):
        return None


def _tree_text(tree: git.Tree, hostname: str) -> str | None:
    """从提交树里取配置原文。

    设备仓库的树根下就是 ``REPO_FILE``；旧共享仓库的历史提交在 ``<hostname>/`` 子目录下。
    两条路径互不重名，顺序试一遍即可同时服务两种仓库。
    """
    for fp in (REPO_FILE, f"{hostname}/{REPO_FILE}"):
        try:
            return tree[fp].data_stream.read().decode("utf-8")
        except KeyError:
            continue
    return None


def init_repo(hostname: str | None = None) -> git.Repo:
    """打开配置仓库。

    ``hostname`` 给定时返回**该设备的独立仓库**（不存在则初始化：``git init`` +
    ``.gitignore`` 初始提交，保证 HEAD 可用；首次初始化会顺带把旧共享仓库里该设备的
    历史重放进来并回写 configs 表的 commit hash）。

    不传参数保持原语义，返回共享仓库根——仅留给兼容调用方；读旧数据走
    :func:`_legacy_repo`（它不会创建仓库）。
    """
    if hostname is None:
        CONFIG_REPO_PATH.mkdir(parents=True, exist_ok=True)
        if not (CONFIG_REPO_PATH / ".git").exists():
            repo = git.Repo.init(str(CONFIG_REPO_PATH))
            _write_gitignore(CONFIG_REPO_PATH)
            repo.index.add([".gitignore"])
            repo.index.commit("init: 初始化配置仓库")
        return git.Repo(str(CONFIG_REPO_PATH))

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
    """首次打开设备仓库时：把旧共享仓库里该设备的历史重放进来，并回写 configs 表的 hash。

    重放 = 逐个版本读出原文、在新仓库里按旧的 message / 作者 / 时间重新提交。
    父链不同 ⇒ hash 必然改变，所以 DeviceConfig 里指向旧 hash 的记录必须回写，
    否则配置历史页与 configs 表对不上、重解析会拿到「Git 无配置」。
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
            c.message,
            author=c.author,
            committer=c.committer,
            author_date=c.authored_datetime,
            commit_date=c.committed_datetime,
        )
        mapping[c.hexsha] = new.hexsha
    if not mapping:
        return
    logger.info("已重放共享仓库历史 hostname=%s：%d 个提交", hostname, len(mapping))
    _remap_config_hashes(hostname, legacy, legacy_fp, mapping)


def _remap_config_hashes(hostname: str, legacy: git.Repo, legacy_fp: str, mapping: dict[str, str]) -> None:
    try:
        from assets.models import DeviceConfig
    except ImportError:  # pragma: no cover - 非 Django 上下文
        return
    try:
        rows = list(DeviceConfig.objects.filter(device__hostname=hostname, git_commit_hash__in=mapping))
        for row in rows:
            row.git_commit_hash = mapping[row.git_commit_hash]
        if rows:
            DeviceConfig.objects.bulk_update(rows, ["git_commit_hash"])

        # 历史 bug（早退返回 HEAD）产生过指向**其它设备 commit** 的脏行：那个 hash 没被重放，
        # 用它反查「≤该时点、真正改过本设备文件的提交」，映射到重放后的对应版本。
        for row in DeviceConfig.objects.filter(device__hostname=hostname).exclude(git_commit_hash__in=mapping):
            try:
                anchor = next(legacy.iter_commits(rev=row.git_commit_hash, paths=legacy_fp, max_count=1))
            except (StopIteration, git.exc.GitCommandError, gitdb.exc.BadName, ValueError):
                continue  # 假 hash（测试数据等）：保持原样，读取兜底也查不到
            new = mapping.get(anchor.hexsha)
            if new and new != row.git_commit_hash:
                row.git_commit_hash = new
                row.save(update_fields=["git_commit_hash"])
    except Exception:
        logger.exception("回写 DeviceConfig.git_commit_hash 失败 hostname=%s（旧 hash 由读取兜底）", hostname)


def save_config(hostname: str, config_text: str, message: str = "") -> str:
    repo = init_repo(hostname)
    config_file = _device_dir(hostname) / REPO_FILE

    try:
        old = repo.head.commit.tree[REPO_FILE].data_stream.read().decode("utf-8")
        if old == config_text:
            # 内容没变：不写文件、不建提交，返回**本设备**自己的上一次提交
            # （独立仓库保证 HEAD 不会是别人的 commit，configs 表去重因此天然命中）
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
    base = Path(CONFIG_REPO_PATH)
    if not base.exists():
        return []
    devices = []
    for item in base.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            if (item / REPO_FILE).exists():
                devices.append(item.name)
    return sorted(devices)
