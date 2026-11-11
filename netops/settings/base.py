"""Django settings 基础层：所有「可被环境变量影响」的配置在这里只定义一遍。

环境区分靠注入不同的值，不靠各环境重写读取逻辑；三个环境文件只放环境变量表达不了的
硬差异（dev 空壳 / container 两条 host 守卫 / prod 的 DEBUG 与 5 项守卫）。
凭据链 `*_FILE > 同名环境变量 > 默认值`（_env_or_file）：`*_FILE` 在容器里指向
/run/secrets/*，宿主可用 envs/host.env 给相对路径（按 BASE_DIR 解析）。

宿主直跑时下面的 load_dotenv 把 envs/*.env 兜底补进进程环境（容器由 compose 注入）。

硬规矩（防循环导入）：本文件与三个环境文件禁止 `from netops.settings import ...` /
`from . import ...`——反向依赖父包执行结果会在 `__init__` 半初始化时炸。

环境变量全表、守卫矩阵与分层理由：handbook/settings.md
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent.parent.resolve()
ENVS_DIR = BASE_DIR / "envs"

# 环境文件三层（谁维护什么见 envs/README.md）——直接部署与 compose 部署读同一份配置：
#   common.env    共享值，唯一需要日常维护；容器经 compose env_file 注入为真实环境
#                 变量，宿主由下面的 load_dotenv 补进进程环境，殊途同归
#   container.env 容器差异（HOST=db/redis、*_FILE=/run/secrets/*、DJANGO_ENV=container）
#   host.env      宿主差异（HOST=localhost 等）；容器里代码卷也带着 envs/，必须按
#                 DJANGO_ENV 区分，否则宿主值会泄进容器
# override=False：真实进程环境（compose 注入 / 手工 export）永远优先，文件只是兜底。
# NETOPS_SKIP_DOTENV=1：全部跳过（tests/deploy 用它拿到纯净默认值，不吃本地 envs/ 的值）。
if os.environ.get("NETOPS_SKIP_DOTENV") != "1":
    load_dotenv(ENVS_DIR / "common.env")
    if os.environ.get("DJANGO_ENV", "dev") != "container":
        load_dotenv(ENVS_DIR / "host.env")


def _env_list(name: str, default: str = "") -> list[str]:
    """逗号分隔的环境变量 → 列表（去空白、丢空项）；未设置时用 default。"""
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


def _env_or_file(name: str, default: str = "") -> str:
    """读一个配置值：`<NAME>_FILE` 指向的文件优先（Docker secrets），其次环境变量，最后默认值。

    文件存在但读不出来时直接报错（ImproperlyConfigured）：静默回退默认值只会把
    「密钥配错了」伪装成「数据库连不上」。内容 strip()，与 postgres 官方 entrypoint
    的 `$(cat file)` 行为一致，否则结尾换行会变成密码的一部分。

    使用约定：*_FILE 在容器里由 envs/container.env 指向 /run/secrets/*；宿主直跑默认
    不设 *_FILE、自然走同名环境变量层，想共用同一份密钥文件时在 envs/host.env 里给
    **相对路径**（相对本文件的 BASE_DIR 解析）——链路统一，不分叉。
    """
    from django.core.exceptions import ImproperlyConfigured

    path = os.environ.get(f"{name}_FILE")
    if path:
        file = Path(path)
        if not file.is_absolute():
            # 相对路径按 BASE_DIR 解析：host.env 里可写 envs/secrets/*，宿主与容器
            # 共用同一份密钥文件；容器内是绝对路径 /run/secrets/*，不受影响。
            file = BASE_DIR / file
        try:
            return file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ImproperlyConfigured(f"{name}_FILE={path} 读取失败：{exc}") from exc
    return os.environ.get(name, default)


# 密钥：未设置时沿用开发期密钥；生产必须注入（prod.py 查 os.environ 原始值，不吃 fallback）。
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or "django-insecure-bua49zfleexo##5iy2q^dm@880a5kdvh5q6%1zss&p#xe1y13$"

# 默认开；prod.py 硬覆盖为 False——生产的 DEBUG 不吃环境变量后门。
DEBUG = os.environ.get("DJANGO_DEBUG", "1").lower() in ("1", "true", "yes")

# 业务日志级别（见下方 LOGGING）：默认 INFO——consumer 这类常驻进程正常运行时只有
# INFO 级输出，调高就又回到「日志文件是空的」。生产嫌吵可设 WARNING。
LOG_LEVEL = os.environ.get("DJANGO_LOG_LEVEL", "INFO").upper()

# 默认放开（无域名阶段）；nginx 透传原样 Host（含端口），Django 校验时剥端口再比对。
ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS", "*")

# 正常拓扑留空即可（Origin 天然等于当前 host）；只有「浏览器看到的来源 ≠ 转给 Django 的
# Host」时才需要声明（外层 LB 改写 Host、TLS 提前终结）。值带 scheme，逗号分隔。
CSRF_TRUSTED_ORIGINS = _env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# 默认值是宿主本机语义（dev 无 env 即此值）；容器由 envs/container.env 注入 HOST=db
# 与 *_FILE=/run/secrets/*，prod.py 守卫要求 HOST 必填。
# 写 127.0.0.1 而不是 localhost：Windows 上 localhost 优先解析成 ::1，而 PostgreSQL / Redis
# 通常只监听 IPv4，psycopg2 与 redis-py 会逐个地址回退——每次连接白等约 10s（实测 10.03s
# vs 0.03s）。pytest 一个会话要建两三条连接，setup 就被拖成 40s 级。
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "netops"),
        "USER": _env_or_file("POSTGRES_USER", "netops"),
        "PASSWORD": _env_or_file("POSTGRES_PASSWORD", "netops_password"),
        "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "PORT": int(os.environ.get("POSTGRES_PORT", "5432")),
    }
}

# 默认宿主本机（理由同上：localhost 在 Windows 上会先试 ::1，Redis 也只监听 IPv4）；
# 容器注入 REDIS_HOST=redis；redis 官方镜像没有 *_FILE 机制，密码只走环境变量。
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

# 访问流（AccessFlow）重建链路的旋钮：阈值口径、取值理由与任务名三处对账见 handbook/analysis.md
ACCESS_FLOW_MAX_QUEUE = int(os.environ.get("ACCESS_FLOW_MAX_QUEUE", "500"))
ACCESS_FLOW_DISPATCH = os.environ.get("ACCESS_FLOW_DISPATCH", "1").lower() in ("1", "true", "yes")
ACCESS_FLOW_TASK = "analysis.rebuild_access_flows"

# Dashboard 采集 / 写库两段链路（采集在 ingest、存储在 analysis，两者只认任务名字符串）：
# - DASHBOARD_WRITE_TASK 是唯一定义处：ingest.tasks.collect_dashboard 按它 send_task
#   （不 import analysis，依赖方向 analysis → ingest 单向），analysis.tasks 的 name=
#   与 tests 的对账断言必须一致。
# - DASHBOARD_PAYLOAD_VIA_REDIS：默认 False = A（payload 随消息直接投递）；True = C
#   （payload 暂存 Redis，只把 key 投递，避免大 payload 塞进 broker 消息）。
DASHBOARD_WRITE_TASK = "analysis.write_dashboard"
DASHBOARD_PAYLOAD_VIA_REDIS = os.environ.get("DASHBOARD_PAYLOAD_VIA_REDIS", "0").lower() in ("1", "true", "yes")
DASHBOARD_PAYLOAD_TTL = int(os.environ.get("DASHBOARD_PAYLOAD_TTL", "600"))

# 链路带宽（只做链路）改为 Zabbix 直取 + Redis 缓存，不落库：
# - conf/links.json 是采集清单与展示 label 的唯一权威；DASHBOARD_LINKS_FILE 是单值路径，
#   容器 /etc/netops/conf/links.json（compose 把宿主 conf/ 只读挂进去）、宿主 conf/links.json；
# - CACHE_TTL 大于 REFRESH_SECONDS：Zabbix 短暂抖动时还能读到上一份；
# - WINDOW_HOURS 是折线窗口（原 analysis.api.dashboard.LINECHART_HOURS）。
DASHBOARD_LINKS_FILE = os.environ.get("DASHBOARD_LINKS_FILE", "conf/links.json")
DASHBOARD_LINK_CACHE_KEY = "dashboard:link:series"
DASHBOARD_LINK_CACHE_TTL = int(os.environ.get("DASHBOARD_LINK_CACHE_TTL", "600"))
DASHBOARD_LINK_REFRESH_SECONDS = int(os.environ.get("DASHBOARD_LINK_REFRESH_SECONDS", "180"))
DASHBOARD_LINK_WINDOW_HOURS = int(os.environ.get("DASHBOARD_LINK_WINDOW_HOURS", "3"))

# 阿里云：一朵云、两个资源集（生产/测试），两套账号共用 region，各产品 endpoint 分别传参。
# 变量清单见 handbook/settings.md；凭据链路同为 *_FILE > 环境变量 > 空。
ALIYUN_CONFIG = {
    "region": os.environ.get("ALIYUN_REGION", ""),
    "endpoints": {
        "Ecs": os.environ.get("ALIYUN_ECS_ENDPOINT", ""),
        "Vpc": os.environ.get("ALIYUN_VPC_ENDPOINT", ""),
        "Slb": os.environ.get("ALIYUN_SLB_ENDPOINT", ""),
        "Sls": os.environ.get("ALIYUN_SLS_ENDPOINT", ""),
        "Asapi": os.environ.get("ALIYUN_ASAPI_ENDPOINT", ""),
    },
    "accounts": {
        "prod": {
            "access_key_id": _env_or_file("ALIYUN_PROD_ACCESS_KEY_ID"),
            "access_key_secret": _env_or_file("ALIYUN_PROD_ACCESS_KEY_SECRET"),
        },
        "test": {
            "access_key_id": _env_or_file("ALIYUN_TEST_ACCESS_KEY_ID"),
            "access_key_secret": _env_or_file("ALIYUN_TEST_ACCESS_KEY_SECRET"),
        },
    },
}

# Dify 知识库（文档转换产物的推送目标）：前三项（base_url / api_key / dataset_id）齐备才启用，
# 缺失时推送接口返 503，转换与留档不受影响。变量清单见 handbook/settings.md。
DIFY_CONFIG = {
    "api_base_url": os.environ.get("DIFY_API_BASE_URL", "").rstrip("/"),
    "api_key": _env_or_file("DIFY_API_KEY"),
    "dataset_id": os.environ.get("DIFY_DATASET_ID", ""),
    "indexing_technique": os.environ.get("DIFY_INDEXING_TECHNIQUE", "high_quality"),
    "timeout": int(os.environ.get("DIFY_TIMEOUT", "30")),
    "process_mode": os.environ.get("DIFY_PROCESS_MODE", "automatic"),
    "segment_separator": os.environ.get("DIFY_SEGMENT_SEPARATOR", "\n"),
    "segment_max_tokens": int(os.environ.get("DIFY_SEGMENT_MAX_TOKENS", "500")),
}


# Zabbix API（ingest 采集器的数据源）：这里只放连接配置，单例与登录逻辑在
# apps/ingest/collectors/zabbix/zabbix.py（get_zapi / close_zapi），未配置 url 则拒绝创建。
# 变量清单与凭据链见 handbook/settings.md；zabbix_utils 自身也读同名 env 兜底，
# 这里显式传参以 settings 为准，行为可预期。
ZABBIX_CONFIG = {
    "url": os.environ.get("ZABBIX_URL", ""),
    "token": _env_or_file("ZABBIX_TOKEN"),
    "user": _env_or_file("ZABBIX_USER"),
    "password": _env_or_file("ZABBIX_PASSWORD"),
    "timeout": int(os.environ.get("ZABBIX_TIMEOUT", "30")),
}


# 以下为环境无关的静态配置

# Logging：业务模块的日志统一走 stderr（Django 的 DEFAULT_LOGGING 只给 django / django.server
# 装了 handler，业务模块 `getLogger(__name__)` 传到 root 无 handler，INFO 全被 lastResort 丢掉）。
# 只给项目自己的命名空间加 handler：不动 root（celery worker 会 hijack root）、不动 Django 默认
# 配置；propagate 保持默认 True，pytest 的 caplog 仍能捕获。输出走 stderr 每次 emit 都 flush，
# 宿主重定向的 data/logs/*.log 与 docker logs 都能实时收到。命令给操作者看的输出不在这里，
# 走 BaseCommand 的 self.stdout / self.stderr。
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
    "loggers": {name: {"handlers": ["netops_console"], "level": LOG_LEVEL} for name in ("core", "ingest", "assets", "analysis", "cloud", "docs", "llmtools", "netops")},
}

# nginx → Django 之间走的是 HTTP，不声明信任该头则 request.is_secure() 恒为 False：
# 启用 HTTPS 后会出现重定向循环、Secure Cookie 不下发、CSRF Origin 校验失败。
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
    "analysis.apps.AnalysisConfig",
    "cloud.apps.CloudConfig",
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
    # OpenAPI 3 schema 生成器（drf-spectacular）
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    # 默认权限：读方法任何已认证用户可用，写方法限操作员（role=operator）或超管，
    # 见 core.permissions.IsOperatorOrReadOnly
    "DEFAULT_PERMISSION_CLASSES": [
        "core.permissions.IsOperatorOrReadOnly",
    ],
    # 列表接口统一启用搜索与排序，各 ViewSet 通过 search_fields / ordering_fields 声明可用字段
    "DEFAULT_FILTER_BACKENDS": [
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    # 列表接口统一数字分页：默认每页 50 条，客户端可用 ?page_size= 覆盖（上限 500）
    "DEFAULT_PAGINATION_CLASS": "netops.pagination.StandardPagination",
    "PAGE_SIZE": 50,
}

# API 文档（OpenAPI 3）：env 动态项按约定只在 base 定义一遍，三个环境文件不重复接线。
# 内网默认放开：schema 只暴露接口元数据、不含业务数据；要收紧就给容器注入
# DJANGO_API_DOCS_REQUIRE_LOGIN=1（IsAuthenticated，可用 /admin/ 登录后的 session 或 Token）。
API_DOCS_PERMISSION = (
    "rest_framework.permissions.IsAuthenticated" if os.environ.get("DJANGO_API_DOCS_REQUIRE_LOGIN", "").lower() in ("1", "true", "yes") else "rest_framework.permissions.AllowAny"
)

SPECTACULAR_SETTINGS = {
    "TITLE": "网络运维管理平台 API",
    "DESCRIPTION": "认证：Authorization: Token <key>（/api/auth/login/ 获取）；写操作限 operator 或超管。",
    "VERSION": "2.0.0",
    # schema 端点自身不出现在文档里
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_PERMISSIONS": [API_DOCS_PERMISSION],
    # 内网不通外网：UI 资源一律走本地 sidecar，collectstatic 后进 /static/ 由 nginx 直出
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

# Celery 行为（与环境无关；broker / result backend 的连接串见上方 Redis 段）
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Asia/Shanghai"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 3600
CELERY_TASK_SOFT_TIME_LIMIT = 3000
# 访问流重建走独立队列（积压可观测），当前由 compose 的 worker 以 -Q celery,access_flow 一并消费
CELERY_TASK_ROUTES = {
    # 键必须等于 ACCESS_FLOW_TASK；改名后 Redis 里的旧消息会 Unknown task，升级前停 worker 清队列
    "analysis.rebuild_access_flows": {"queue": "access_flow"},
}
# 大屏链路缓存周期刷新：beat 只负责按时投递，采集仍由 worker 执行（Zabbix async 客户端
# 只活在 worker 的 event loop 里）。队列走默认 celery，与写入链共用并发槽。
CELERY_BEAT_SCHEDULE = {
    "dashboard-link-cache": {
        "task": "ingest.refresh_link_cache",
        "schedule": DASHBOARD_LINK_REFRESH_SECONDS,
    },
}
