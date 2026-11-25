"""Django settings 基础层：所有可被环境变量影响的配置只在这里定义一遍。

宿主直跑时 load_dotenv 把 envs/*.env 兜底补进进程环境（容器由 compose 注入）。
本文件与三个环境文件禁止 `from netops.settings import ...` / `from . import ...`（半初始化时会炸）。
环境变量全表、守卫矩阵与分层理由：handbook/settings.md
"""

import os
from pathlib import Path

import pymysql
from celery.schedules import crontab
from dotenv import load_dotenv

from .defaults import ENV_DEFAULTS

pymysql.install_as_MySQLdb()


BASE_DIR = Path(__file__).parent.parent.parent.resolve()
ENVS_DIR = BASE_DIR / "envs"

# env 文件分层与 override=False / NETOPS_SKIP_DOTENV 的语义见 envs/README.md 与 handbook/settings.md。
if os.environ.get("NETOPS_SKIP_DOTENV") != "1":
    load_dotenv(ENVS_DIR / "common.env")
    if os.environ.get("DJANGO_ENV", "dev") != "container":
        load_dotenv(ENVS_DIR / "host.env")

# 环境默认值：只在代码里定义、按 DJANGO_ENV 选一套；必须在 load_dotenv 之后读。
_ENV_NAME = os.environ.get("DJANGO_ENV", "dev")
_ENV_DEFAULTS = ENV_DEFAULTS.get(_ENV_NAME, ENV_DEFAULTS["dev"])


def _env_bool(name: str, default: bool) -> bool:
    """布尔环境变量：1/true/yes/on 为真；未设置或空串时用 default。"""
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_list(name: str, default: str = "") -> list[str]:
    """逗号分隔的环境变量 → 列表（去空白、丢空项）；未设置时用 default。"""
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


def _env_or_file(name: str, default: str = "") -> str:
    """读配置值：`<NAME>_FILE` 文件 > 同名环境变量 > default。

    文件存在但读不出来时抛 ImproperlyConfigured（不静默回退）；内容 strip()。
    相对路径按 BASE_DIR 解析，容器里是 /run/secrets/*。详见 handbook/settings.md「凭据链」。
    """
    from django.core.exceptions import ImproperlyConfigured

    path = os.environ.get(f"{name}_FILE")
    if path:
        file = Path(path)
        if not file.is_absolute():
            file = BASE_DIR / file
        try:
            return file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ImproperlyConfigured(f"{name}_FILE={path} 读取失败：{exc}") from exc
    return os.environ.get(name, default)


# 密钥：未设置时沿用开发期密钥；生产必须注入（prod.py 查原始值）。
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or "django-insecure-bua49zfleexo##5iy2q^dm@880a5kdvh5q6%1zss&p#xe1y13$"

# 默认开；prod.py 硬覆盖为 False。
DEBUG = _env_bool("DJANGO_DEBUG", True)

# 业务日志级别（见下方 LOGGING）；默认 INFO。
LOG_LEVEL = os.environ.get("DJANGO_LOG_LEVEL", "INFO").upper()

# 默认放开（无域名阶段）；Django 校验时剥端口再比对。
ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS", "*")

# 正常拓扑留空；只有「浏览器看到的来源 ≠ 转给 Django 的 Host」时才需要声明（带 scheme，逗号分隔）。
CSRF_TRUSTED_ORIGINS = _env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# 数据库后端：postgresql（默认）/ mysql。连接参数统一 DB_*，镜像认的 POSTGRES_* / MYSQL_*
# 由 envs/db.env 嵌套。MySQL 驱动的两阶段构建与宿主依赖见 handbook/settings.md。
DB_ENGINE = os.environ.get("DB_ENGINE", "postgresql").strip().lower()

_DB_BACKENDS = {
    "postgresql": "django.db.backends.postgresql",
    "mysql": "django.db.backends.mysql",
}
_DB_PORTS = {"postgresql": "5432", "mysql": "3306"}

if DB_ENGINE not in _DB_BACKENDS:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(f"DB_ENGINE 只支持 {sorted(_DB_BACKENDS)}，当前是 {DB_ENGINE!r}")


# 默认值是本机语义；容器注入 DB_HOST=db 与 *_FILE。写 127.0.0.1 而不是 localhost：
# Windows 上会先试 ::1，每次连接白等约 10s（见 handbook/settings.md）。
_DATABASE: dict[str, object] = {
    "ENGINE": _DB_BACKENDS[DB_ENGINE],
    "NAME": os.environ.get("DB_NAME", "netops"),
    "USER": _env_or_file("DB_USER", "netops"),
    "PASSWORD": _env_or_file("DB_PASSWORD", "netops_password"),
    "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
    "PORT": int(os.environ.get("DB_PORT", _DB_PORTS[DB_ENGINE])),
}
if DB_ENGINE == "mysql":
    # utf8mb4 才能存四字节字符；不显式给会取决于服务端默认值。
    _DATABASE["OPTIONS"] = {"charset": "utf8mb4"}

DATABASES = {"default": _DATABASE}

# 默认本机（理由同 DB_HOST）；容器注入 REDIS_HOST=redis。redis 官方镜像没有 *_FILE。
REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_DB = int(os.environ.get("REDIS_DB", 0))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "")

if REDIS_PASSWORD:
    REDIS_URL = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
else:
    REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL

# MCP 工具出口（/mcp）：匿名，身份与配额只到客户端 IP（netops/mcp.py）。
# MCP_ENABLED=0 时不建子应用、/mcp 回 404；限流 0 = 不限流。默认值见 settings/defaults.py。
MCP_ENABLED = _env_bool("MCP_ENABLED", _ENV_DEFAULTS["MCP_ENABLED"])
MCP_RATE_LIMIT_PER_MINUTE = int(os.environ.get("MCP_RATE_LIMIT_PER_MINUTE", "60"))

# 访问流重建链路：阈值口径与任务名对账见 handbook/analysis.md。
ACCESS_FLOW_MAX_QUEUE = int(os.environ.get("ACCESS_FLOW_MAX_QUEUE", "500"))
ACCESS_FLOW_DISPATCH = _env_bool("ACCESS_FLOW_DISPATCH", True)
ACCESS_FLOW_TASK = "analysis.rebuild_access_flows"

# 大屏采集 / 写库两段链路：DASHBOARD_WRITE_TASK 是任务名的唯一定义处，
# 与 analysis.tasks 的 name= 及测试对账。payload 方案见 handbook/analysis.md。
DASHBOARD_WRITE_TASK = "analysis.write_dashboard"

# 外部连接健康探活：beat 写 core.IntegrationHealth，API 只读。任务名与 core/tasks.py 对账。
INTEGRATION_PROBE_TASK = "core.integrations.probe_all"
INTEGRATION_PROBE_SECONDS = int(os.environ.get("INTEGRATION_PROBE_SECONDS", "300"))

# 大屏 payload 投递方案：False = 随消息直投；True = 暂存 Redis、只投 key（TTL 见下一项）。
DASHBOARD_PAYLOAD_VIA_REDIS = _env_bool("DASHBOARD_PAYLOAD_VIA_REDIS", False)
DASHBOARD_PAYLOAD_TTL = int(os.environ.get("DASHBOARD_PAYLOAD_TTL", "600"))

# 设备组（zabbix）与工单 / SLB / 巡检（autotask）的采集周期：beat 投递
# ingest.collect_dashboard(source)。单位秒，必须 > 0（0 等于每轮重投）。
DASHBOARD_COLLECT_SECONDS = int(os.environ.get("DASHBOARD_COLLECT_SECONDS", "180"))
DASHBOARD_AUTOTASK_SECONDS = int(os.environ.get("DASHBOARD_AUTOTASK_SECONDS", "600"))

# 链路带宽走 Zabbix 直取 + Redis 缓存，不落库：conf/links.json 是采集清单的唯一权威。
DASHBOARD_LINKS_FILE = os.environ.get("DASHBOARD_LINKS_FILE", "conf/links.json")
DASHBOARD_LINK_CACHE_KEY = "dashboard:link:series"
DASHBOARD_LINK_CACHE_TTL = int(os.environ.get("DASHBOARD_LINK_CACHE_TTL", "600"))
DASHBOARD_LINK_REFRESH_SECONDS = int(os.environ.get("DASHBOARD_LINK_REFRESH_SECONDS", "180"))
DASHBOARD_LINK_WINDOW_HOURS = int(os.environ.get("DASHBOARD_LINK_WINDOW_HOURS", "3"))

# 巡检：每日采集前一天（可传区间补数）的 CPU / 内存 / 接口带宽，落 analysis 日表。
# 任务名只在这里定义一遍（与 analysis / ingest 的装饰器 name= 及测试对账）；
# INSPECTION_RETENTION_DAYS 按业务日期滚存，0 = 永久保留（清理任务直接跳过）。
# 链路与口径见 handbook/analysis.md「巡检」。
INSPECTION_DISPATCH_TASK = "analysis.dispatch_inspection"
INSPECTION_COLLECT_TASK = "ingest.collect_inspection"
INSPECTION_WRITE_TASK = "analysis.write_inspection"
INSPECTION_PRUNE_TASK = "analysis.prune_inspection"
INSPECTION_DISPATCH_HOUR = os.environ.get("INSPECTION_DISPATCH_HOUR", "6")
INSPECTION_DISPATCH_MINUTE = os.environ.get("INSPECTION_DISPATCH_MINUTE", "0")
INSPECTION_PRUNE_HOUR = os.environ.get("INSPECTION_PRUNE_HOUR", "6")
INSPECTION_PRUNE_MINUTE = os.environ.get("INSPECTION_PRUNE_MINUTE", "40")
INSPECTION_RETENTION_DAYS = int(os.environ.get("INSPECTION_RETENTION_DAYS", "365"))

# 外部连接配置：Zabbix / 阿里云 / Dify / autotask 共用 base_url / credential_ref /
# timeout / enabled；消费方统一看 enabled。字段语义与变量清单见 handbook/settings.md。
_ALIYUN_REGION = os.environ.get("ALIYUN_REGION", "")
_ALIYUN_ACCOUNTS = {
    "prod": {
        "access_key_id": _env_or_file("ALIYUN_PROD_ACCESS_KEY_ID"),
        "access_key_secret": _env_or_file("ALIYUN_PROD_ACCESS_KEY_SECRET"),
    },
    "test": {
        "access_key_id": _env_or_file("ALIYUN_TEST_ACCESS_KEY_ID"),
        "access_key_secret": _env_or_file("ALIYUN_TEST_ACCESS_KEY_SECRET"),
    },
}
ALIYUN_CONFIG = {
    "base_url": "",
    "credential_ref": "ALIYUN_{PROD,TEST}_ACCESS_KEY_ID/_SECRET",
    "timeout": int(os.environ.get("ALIYUN_TIMEOUT", "30")),
    "region": _ALIYUN_REGION,
    "endpoints": {
        "Ecs": os.environ.get("ALIYUN_ECS_ENDPOINT", ""),
        "Vpc": os.environ.get("ALIYUN_VPC_ENDPOINT", ""),
        "Slb": os.environ.get("ALIYUN_SLB_ENDPOINT", ""),
        "Sls": os.environ.get("ALIYUN_SLS_ENDPOINT", ""),
        "Asapi": os.environ.get("ALIYUN_ASAPI_ENDPOINT", ""),
    },
    "accounts": _ALIYUN_ACCOUNTS,
    "enabled": bool(_ALIYUN_REGION) and any(a["access_key_id"] and a["access_key_secret"] for a in _ALIYUN_ACCOUNTS.values()),
}

# Dify 知识库：base_url / api_key / dataset_id 齐备才启用，缺失时推送接口返回 503。
_DIFY_BASE_URL = os.environ.get("DIFY_API_BASE_URL", "").rstrip("/")
_DIFY_API_KEY = _env_or_file("DIFY_API_KEY")
_DIFY_DATASET_ID = os.environ.get("DIFY_DATASET_ID", "")
DIFY_CONFIG = {
    "base_url": _DIFY_BASE_URL,
    "credential_ref": "DIFY_API_KEY",
    "timeout": int(os.environ.get("DIFY_TIMEOUT", "30")),
    "enabled": bool(_DIFY_BASE_URL and _DIFY_API_KEY and _DIFY_DATASET_ID),
    "api_key": _DIFY_API_KEY,
    "dataset_id": _DIFY_DATASET_ID,
    "indexing_technique": os.environ.get("DIFY_INDEXING_TECHNIQUE", "high_quality"),
    "process_mode": os.environ.get("DIFY_PROCESS_MODE", "automatic"),
    "segment_separator": os.environ.get("DIFY_SEGMENT_SEPARATOR", "\n"),
    "segment_max_tokens": int(os.environ.get("DIFY_SEGMENT_MAX_TOKENS", "500")),
}

# Zabbix API：单例与登录逻辑在 core/integrations/providers/zabbix/client.py；
# 显式传参以 settings 为准（不依赖 zabbix_utils 自己读 env）。
_ZABBIX_BASE_URL = os.environ.get("ZABBIX_URL", "").rstrip("/")
_ZABBIX_TOKEN = _env_or_file("ZABBIX_TOKEN")
_ZABBIX_USER = _env_or_file("ZABBIX_USER")
_ZABBIX_PASSWORD = _env_or_file("ZABBIX_PASSWORD")
ZABBIX_CONFIG = {
    "base_url": _ZABBIX_BASE_URL,
    "credential_ref": "ZABBIX_TOKEN" if _ZABBIX_TOKEN else "ZABBIX_USER/ZABBIX_PASSWORD",
    "timeout": int(os.environ.get("ZABBIX_TIMEOUT", "30")),
    "enabled": bool(_ZABBIX_BASE_URL and (_ZABBIX_TOKEN or (_ZABBIX_USER and _ZABBIX_PASSWORD))),
    "token": _ZABBIX_TOKEN,
    "user": _ZABBIX_USER,
    "password": _ZABBIX_PASSWORD,
}

# autotask：内网 HTTP 服务，无凭据；未配置则大屏的 autotask 源失败。
_AUTOTASK_BASE_URL = os.environ.get("AUTOTASK_BASE_URL", "").rstrip("/")
AUTOTASK_CONFIG = {
    "base_url": _AUTOTASK_BASE_URL,
    "credential_ref": "",
    "timeout": int(os.environ.get("AUTOTASK_TIMEOUT", "30")),
    "enabled": bool(_AUTOTASK_BASE_URL),
}


# Git 配置仓库：每台设备一个独立仓库 <CONFIG_REPO_PATH>/<hostname>/。
# 默认 <项目根>/data/config_repo；容器覆盖成命名卷挂载点。每次调用都重新读。
CONFIG_REPO_PATH = Path(os.environ.get("CONFIG_REPO_PATH", str(BASE_DIR / "data" / "config_repo")))


# 以下为环境无关的静态配置

# Logging：只给项目命名空间装 stderr handler，不动 root、propagate 保持 True。
# 级别取 DJANGO_LOG_LEVEL；理由见 handbook/settings.md。
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "netops_console": {
            "format": "%(asctime)s %(levelname)s %(name)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "netops_console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "formatter": "netops_console",
            "level": LOG_LEVEL,
        },
    },
    "loggers": {name: {"handlers": ["netops_console"], "level": LOG_LEVEL} for name in ("core", "ingest", "assets", "analysis", "docs", "llmtools", "netops")},
}

# nginx → Django 走 HTTP；不信任该头会让 is_secure() 恒为 False（HTTPS 下重定向循环等）。
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",
    # OpenAPI 3 文档：sidecar 把 Swagger UI / ReDoc 静态资源带进 collectstatic
    "drf_spectacular",
    "drf_spectacular_sidecar",
    # GinIndex（analysis.AccessFlow 的 device_ids / policy_ids）要求这个 app 在册
    "django.contrib.postgres",
    "core.apps.CoreConfig",
    "ingest.apps.OperatorConfig",
    "assets.apps.AssetsConfig",
    # 配置域：configs → assets（Device 外键），所以排在 assets 之后
    "configs.apps.ConfigsConfig",
    "analysis.apps.AnalysisConfig",
    "docs.apps.DocsConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "netops.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "netops.wsgi.application"


AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


LANGUAGE_CODE = "zh-hans"

TIME_ZONE = "Asia/Shanghai"

USE_I18N = True

USE_TZ = True

STATIC_URL = "/static/"
FRONTEND = BASE_DIR / "frontend" / "dist"
STATIC_ROOT = BASE_DIR / "www"

MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.console.EmailBackend",
    },
}
AUTH_USER_MODEL = "core.User"

# DRF
REST_FRAMEWORK = {
    # OpenAPI 3 schema 生成器
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    # 读对已认证用户开放，写限 operator 或超管（core.permissions.IsOperatorOrReadOnly）
    "DEFAULT_PERMISSION_CLASSES": [
        "core.permissions.IsOperatorOrReadOnly",
    ],
    # 列表接口统一搜索与排序（各 ViewSet 声明 search_fields / ordering_fields）
    "DEFAULT_FILTER_BACKENDS": [
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    # 默认每页 50 条，?page_size= 可覆盖（上限 500）
    "DEFAULT_PAGINATION_CLASS": "netops.pagination.StandardPagination",
    "PAGE_SIZE": 50,
}

# API 文档（OpenAPI 3）：是否登录按环境给默认，env 可覆盖；见 handbook/api.md。
_DOCS_REQUIRE_LOGIN = _env_bool("DJANGO_API_DOCS_REQUIRE_LOGIN", _ENV_DEFAULTS["DJANGO_API_DOCS_REQUIRE_LOGIN"])
API_DOCS_PERMISSION = "rest_framework.permissions.IsAuthenticated" if _DOCS_REQUIRE_LOGIN else "rest_framework.permissions.AllowAny"

SPECTACULAR_SETTINGS = {
    "TITLE": "网络运维管理平台 API",
    "DESCRIPTION": "认证：Authorization: Token <key>（/api/auth/login/ 获取）；写操作限 operator 或超管。",
    "VERSION": "2.0.0",
    # schema 端点自身不出现在文档里
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_PERMISSIONS": [API_DOCS_PERMISSION],
    # 内网不通外网：UI 资源走本地 sidecar，collectstatic 后由 nginx 直出
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "REDOC_DIST": "SIDECAR",
    "SWAGGER_UI_SETTINGS": {
        "persistAuthorization": True,
        "deepLinking": True,
        "displayRequestDuration": True,
        "docExpansion": "list",
        "defaultModelsExpandDepth": -1,
        "filter": True,
    },
}

# Celery 行为（与环境无关；broker / result backend 连接串见上方 Redis 段）
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Asia/Shanghai"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 3600
CELERY_TASK_SOFT_TIME_LIMIT = 3000
# 访问流重建走独立队列（由 worker 以 -Q celery,access_flow 一并消费）
CELERY_TASK_ROUTES = {
    # 键必须等于 ACCESS_FLOW_TASK；改名要让旧消息消费完再滚（否则 Unknown task）
    "analysis.rebuild_access_flows": {"queue": "access_flow"},
}
# 大屏三条周期链由内置 beat 投递；条目名固定，改名等于换调度。
CELERY_BEAT_SCHEDULE = {
    # 外部连接健康状态：探活结果落 core.IntegrationHealth（API 只读，跨进程可见）
    "integration-health": {
        "task": INTEGRATION_PROBE_TASK,
        "schedule": INTEGRATION_PROBE_SECONDS,
    },
    "dashboard-link-cache": {
        "task": "ingest.refresh_link_cache",
        "schedule": DASHBOARD_LINK_REFRESH_SECONDS,
    },
    # args 就是 collect_dashboard 的 source 参数（未知 source 会抛 ValueError）
    "dashboard-collect-zabbix": {
        "task": "ingest.collect_dashboard",
        "schedule": DASHBOARD_COLLECT_SECONDS,
        "args": ("zabbix",),
    },
    "dashboard-collect-autotask": {
        "task": "ingest.collect_dashboard",
        "schedule": DASHBOARD_AUTOTASK_SECONDS,
        "args": ("autotask",),
    },
    # 巡检：先投采集（读目标清单 → 采 Zabbix → 投写库），再滚存清理超过保留期的日表
    "inspection-dispatch": {
        "task": INSPECTION_DISPATCH_TASK,
        "schedule": crontab(hour=INSPECTION_DISPATCH_HOUR, minute=INSPECTION_DISPATCH_MINUTE),
    },
    "inspection-prune": {
        "task": INSPECTION_PRUNE_TASK,
        "schedule": crontab(hour=INSPECTION_PRUNE_HOUR, minute=INSPECTION_PRUNE_MINUTE),
    },
}
