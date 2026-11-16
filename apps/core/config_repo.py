"""Git 配置仓库管理

**每台设备一个独立仓库**：``settings.CONFIG_REPO_PATH/<hostname>/``，仓库根就是该设备目录，
入库的只有 ``running-config.txt``（设备目录里放的其它源文件不入库）。

为什么不再共用一条线性链：共享链的 HEAD 属于「最后提交的那台设备」，``save_config``
在新旧内容相同时直接返回 HEAD——设备交替导入时会把**别的设备的 commit** 当结果返回，
configs 表按 ``(device, git_commit_hash)`` 去重便误判成新版本（重复记录 + 重复解析，
且该 commit 在本设备的文件历史里根本不存在）。独立仓库后每台设备的 HEAD 就是自己
最后一次提交，内容未变即返回自己的旧 hash，去重天然正确。

存量迁移（**首次打开某设备仓库时自动执行**）：若存在旧的共享仓库（``settings.CONFIG_REPO_PATH/.git``，
只读兜底、不主动创建），把该设备在其中的历史**逐条重放**进新仓库（保留 message / 作者 /
提交时间；父链变了，hash 必然不同），随后通过**注册的 hash 回写钩子**把 configs 表
``DeviceConfig.git_commit_hash`` 指向旧 hash 的记录回写成新 hash。回写覆盖不到的旧 hash
（回写失败、历史 bug 产生的脏行）由读取路径兜底：``get_config`` / ``diff_configs``
查不到时回退读共享仓库，不会出现「Git 无配置」。

**为什么在 core**：它是「配置原文的存储层」——写侧是 ingest 的入库链路，读侧是
``ingest/api/configs.py`` 的快照 / diff / 历史接口，`scripts/purge_configs.py` 还要删整个
目录。放在任一业务域里，另一边就只能反向依赖；git 操作与设备台账、解析规则都无关，
属于平台级基础设施（同 ``core/queue_*`` 的定位）。

**为什么 DeviceConfig 的 hash 回写是钩子**：core 不许 import 任何业务域（见
``tests/core/test_layering.py``），而 ``DeviceConfig`` 是 configs 的表。所以 core 只提供
「重放完成 + 新老 hash 映射」这个钩子点（``register_hash_remapper``）与锚点查询
（``legacy_commit_for``），实现放在 ``configs/repo_hashes.py``，由 configs 在 ``ready()`` 注册。
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
    """仓库根目录：读 ``settings.CONFIG_REPO_PATH``。

    **每次调用都读**，不缓存成模块常量：路径的唯一来源是 settings（env ``CONFIG_REPO_PATH``
    覆盖），测试用 ``override_settings(CONFIG_REPO_PATH=tmp_path)`` 即可换目录，不必 monkeypatch
    模块属性——那种做法会让「配置从哪来」在代码里出现两份答案。
    """
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

    给 hash 回写钩子用：历史 bug（内容未变时早退返回 HEAD）留下过指向**其它设备 commit**
    的脏行，那个 hash 不在重放映射里，需要用这个锚点换算出重放后的对应版本。
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
    base = repo_root()
    if not base.exists():
        return []
    devices = []
    for item in base.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            if (item / REPO_FILE).exists():
                devices.append(item.name)
    return sorted(devices)
