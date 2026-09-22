"""settings 的分发与守卫：DJANGO_ENV 白名单、base 的 env 动态链、container/prod 守卫。

架构（见 netops/settings/）：env 动态项在 base 只定义一遍；环境文件只放不走环境变量的
硬差异与守卫——dev 空壳、container 两条 host 必填守卫、prod DEBUG=False + 5 个必填守卫。
因此所有用例都走**分发**（purge 包与环境子模块 → 设 DJANGO_ENV → 重新 import 包），
而不是直 import 环境模块——环境文件在新架构下不是自包含配置，只是覆盖层。
"""

import importlib
import sys

import pytest
from django.core.exceptions import ImproperlyConfigured

# prod 配齐时的最小环境（测试不依赖宿主是否 export 过这些变量）
PROD_REQUIRED = {
    "DJANGO_SECRET_KEY": "test-secret-key-for-prod",
    "DJANGO_ALLOWED_HOSTS": "netops.example.com",
    "POSTGRES_HOST": "db.internal",
    "POSTGRES_PASSWORD": "s3cret",
    "REDIS_HOST": "redis.internal",
}

# 每次 dispatch 前清掉的键，避免宿主/前一个用例的残留影响默认值断言
_MANAGED_KEYS = (
    "DJANGO_ENV",
    "DJANGO_DEBUG",
    *PROD_REQUIRED,
    "POSTGRES_PASSWORD_FILE",
    "POSTGRES_USER",
    "POSTGRES_DB",
    "POSTGRES_PORT",
    "REDIS_PORT",
    "REDIS_DB",
    "REDIS_PASSWORD",
)


def _purge():
    """清掉包与全部环境子模块——环境/守卫在 import 时执行，留缓存会拿到旧状态。"""
    for name in [m for m in sys.modules if m == "netops.settings" or m.startswith("netops.settings.")]:
        sys.modules.pop(name)


def _dispatch(monkeypatch, django_env=None, **env):
    """清场 → 设 DJANGO_ENV 与配套变量 → 重新 import netops.settings（触发分发）。"""
    for key in _MANAGED_KEYS:
        monkeypatch.delenv(key, raising=False)
    if django_env is not None:
        monkeypatch.setenv("DJANGO_ENV", django_env)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    _purge()
    return importlib.import_module("netops.settings")


# ---------------------------------------------------------------------------
# 分发矩阵
# ---------------------------------------------------------------------------


def test_dev_is_default(monkeypatch):
    """不设 DJANGO_ENV → dev：base 的默认语义 localhost / DEBUG=True / HOSTS=['*']。"""
    m = _dispatch(monkeypatch)
    assert m.DEBUG is True
    assert m.ALLOWED_HOSTS == ["*"]
    assert m.DATABASES["default"]["HOST"] == "localhost"
    assert m.REDIS_HOST == "localhost"
    assert m.CELERY_BROKER_URL == m.REDIS_URL


def test_container_overrides_via_injection(monkeypatch):
    """container 的差异靠 env 注入表达：HOST=db/redis 覆盖 base 的 localhost 默认。"""
    m = _dispatch(monkeypatch, "container", POSTGRES_HOST="db", REDIS_HOST="redis")
    assert m.DATABASES["default"]["HOST"] == "db"    # 注入值胜过 base 默认
    assert m.REDIS_HOST == "redis"
    assert m.DEBUG is True                            # 未设 DJANGO_DEBUG 时默认开


def test_django_debug_env_dynamic(monkeypatch):
    """DJANGO_DEBUG 是 base 的 env 动态项：container 分发下设 0 即关闭。"""
    m = _dispatch(monkeypatch, "container", POSTGRES_HOST="db", REDIS_HOST="redis", DJANGO_DEBUG="0")
    assert m.DEBUG is False


@pytest.mark.parametrize("missing", ["POSTGRES_HOST", "REDIS_HOST"])
def test_container_rejects_missing_host(monkeypatch, missing):
    """container 守卫：两个 host 由 env_file 注入，缺一个启动即拒（不退 base 默认）。"""
    hosts = {"POSTGRES_HOST": "db", "REDIS_HOST": "redis"}
    hosts.pop(missing)
    with pytest.raises(ImproperlyConfigured, match=missing):
        _dispatch(monkeypatch, "container", **hosts)


def test_container_reports_all_missing_at_once(monkeypatch):
    """缺多个一次报全：两个 host 都缺时只抛一条，且同时点名两个键。"""
    with pytest.raises(ImproperlyConfigured) as exc:
        _dispatch(monkeypatch, "container")
    message = str(exc.value)
    assert "POSTGRES_HOST" in message
    assert "REDIS_HOST" in message
    assert "共 2 个" in message


def test_unknown_django_env_rejected(monkeypatch):
    """白名单：未知 DJANGO_ENV（拼错如 prd）拒绝启动，不许静默落 dev。"""
    with pytest.raises(ImproperlyConfigured, match="未知 DJANGO_ENV='prd'"):
        _dispatch(monkeypatch, "prd")


# ---------------------------------------------------------------------------
# prod：DEBUG 硬覆盖 + 5 个必填守卫（查 os.environ 原始值，启动即拒）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("missing", "needle"),
    [
        ("DJANGO_SECRET_KEY", "DJANGO_SECRET_KEY"),
        ("DJANGO_ALLOWED_HOSTS", "DJANGO_ALLOWED_HOSTS"),
        ("POSTGRES_HOST", "POSTGRES_HOST"),
        ("POSTGRES_PASSWORD", "POSTGRES_PASSWORD"),
        ("REDIS_HOST", "REDIS_HOST"),
    ],
)
def test_prod_rejects_missing_required(monkeypatch, missing, needle):
    """五个必填项各缺一次都必须拒绝启动，且报错指向缺的那个键。"""
    env = {k: v for k, v in PROD_REQUIRED.items() if k != missing}
    with pytest.raises(ImproperlyConfigured, match=needle):
        _dispatch(monkeypatch, "prod", **env)


def test_prod_rejects_wildcard_hosts(monkeypatch):
    """ALLOWED_HOSTS 显式给 '*' 同样拒绝——生产不许全放开。"""
    with pytest.raises(ImproperlyConfigured, match="不允许"):
        _dispatch(monkeypatch, "prod", **{**PROD_REQUIRED, "DJANGO_ALLOWED_HOSTS": "*"})


def test_prod_reports_all_missing_at_once(monkeypatch):
    """一次报全：五项全缺只抛一条异常，消息同时点名全部缺失项（不做挤牙膏式失败）。"""
    with pytest.raises(ImproperlyConfigured) as exc:
        _dispatch(monkeypatch, "prod")   # _dispatch 会清空 PROD_REQUIRED 全部键
    message = str(exc.value)
    for key in PROD_REQUIRED:
        assert key in message, f"报错未点名 {key}：{message}"
    assert "共 5 项" in message


def test_prod_loads_when_complete(monkeypatch):
    """环境齐全时 prod 正常分发：DEBUG=False、注入值全部生效。"""
    m = _dispatch(monkeypatch, "prod", **PROD_REQUIRED)
    assert m.DEBUG is False
    assert m.ALLOWED_HOSTS == ["netops.example.com"]
    assert m.DATABASES["default"]["HOST"] == "db.internal"
    assert m.REDIS_HOST == "redis.internal"


def test_prod_debug_hard_false(monkeypatch):
    """prod 的 DEBUG 是硬覆盖：设了 DJANGO_DEBUG=1 也无效（不吃环境变量后门）。"""
    m = _dispatch(monkeypatch, "prod", **PROD_REQUIRED, DJANGO_DEBUG="1")
    assert m.DEBUG is False


# ---------------------------------------------------------------------------
# base 的 env 动态链（凭据三级：*_FILE > 同名环境变量 > 默认值；三环境统一）
# ---------------------------------------------------------------------------


def test_credential_chain_file_env_default(monkeypatch, tmp_path):
    """同一段 base 代码三级链各命中一次；宿主（dev 分发）与容器共用，不分叉。"""
    secret = tmp_path / "pg_password"
    secret.write_text("from-file\n", encoding="utf-8")   # 尾换行必须被 strip

    m = _dispatch(monkeypatch, POSTGRES_PASSWORD_FILE=str(secret))
    assert m.DATABASES["default"]["PASSWORD"] == "from-file"

    m = _dispatch(monkeypatch, POSTGRES_PASSWORD="from-env")
    assert m.DATABASES["default"]["PASSWORD"] == "from-env"

    m = _dispatch(monkeypatch)  # 都不设 → base 默认值
    assert m.DATABASES["default"]["PASSWORD"] == "netops_password"
