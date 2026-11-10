"""Django settings 基础层：所有「可被环境变量影响」的配置在这里只定义一遍。

环境区分靠注入不同的值，不靠各环境重写读取逻辑；三个环境文件只放环境变量表达不了的
硬差异（dev 空壳 / container 两条 host 守卫 / prod 的 DEBUG 与 5 项守卫）。
凭据链 `*_FILE > 同名环境变量 > 默认值`（_env_or_file），`*_FILE` 只在容器里设置。

硬规矩（防循环导入）：本文件与三个环境文件禁止 `from netops.settings import ...` /
`from . import ...`——反向依赖父包执行结果会在 `__init__` 半初始化时炸。

环境变量全表、守卫矩阵与分层理由：handbook/settings.md
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).parent.parent.parent.resolve()


def _env_list(name: str, default: str = "") -> list[str]:
    """逗号分隔的环境变量 → 列表（去空白、丢空项）；未设置时用 default。"""
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


def _env_or_file(name: str, default: str = "") -> str:
    """读一个配置值：`<NAME>_FILE` 指向的文件优先（Docker secrets），其次环境变量，最后默认值。

    文件存在但读不出来时直接报错（ImproperlyConfigured）：静默回退默认值只会把
    「密钥配错了」伪装成「数据库连不上」。内容 strip()，与 postgres 官方 entrypoint
    的 `$(cat file)` 行为一致，否则结尾换行会变成密码的一部分。
    """
    path = os.environ.get(f"{name}_FILE")
    if path:
        try:
            return Path(path).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ImproperlyConfigured(f"{name}_FILE={path} 读取失败：{exc}") from exc
    return os.environ.get(name, default)


# 密钥：未设置时沿用开发期密钥；生产必须注入（prod.py 查 os.environ 原始值，不吃 fallback）。
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or "django-insecure-bua49zfleexo##5iy2q^dm@880a5kdvh5q6%1zss&p#xe1y13$"

# 默认开；prod.py 硬覆盖为 False——生产的 DEBUG 不吃环境变量后门。
DEBUG = os.environ.get("DJANGO_DEBUG", "1").lower() in ("1", "true", "yes")

# 默认放开（无域名阶段）；nginx 透传原样 Host（含端口），Django 校验时剥端口再比对。
ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS", "*")

# 正常拓扑留空即可（Origin 天然等于当前 host）；只有「浏览器看到的来源 ≠ 转给 Django 的
# Host」时才需要声明（外层 LB 改写 Host、TLS 提前终结）。值带 scheme，逗号分隔。
CSRF_TRUSTED_ORIGINS = _env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# 默认值是宿主本机语义（dev 无 env 即此值）；容器由 env/app.env 注入 HOST=db。
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


# 以下为环境无关的静态配置

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
