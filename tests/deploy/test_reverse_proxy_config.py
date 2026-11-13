"""反向代理与 Django 的接口契约（nginx 配置 + compose 环境变量）。

守的是一条**实测踩过的坑**：nginx 用 `proxy_set_header Host $host` 时端口会被丢掉，
宿主机映射到非标准端口（`NGINX_PORT=8000`）后，Django 的 `request.get_host()` 得到
`localhost`，而浏览器的 Origin 是 `http://localhost:8000`——CSRF 的 Origin 校验只认
「当前 host」与 `CSRF_TRUSTED_ORIGINS`，于是登录直接 403：

    Forbidden (Origin checking failed - http://localhost:8000 does not match any
    trusted origins.): /admin/login/

同样的请求只把 Host 从 `localhost:8000` 换成 `localhost`，失败原因就变成
「CSRF cookie not set」——即 Origin 校验已通过。这几条测试分别锁住：nginx 侧必须
透传带端口的 Host、Django 侧「Host 带端口则同源 Origin 可信」的规则、compose 把
`DJANGO_CSRF_TRUSTED_ORIGINS`（在 `envs/common.env` 里）注入全部运行时服务、
按层拆分的 `env_file` 不许串味、以及数据库凭据只从 secrets 读。
"""

import logging
import re

import pytest
from django.conf import settings
from django.test import Client

NGINX_CONF_DIR = settings.BASE_DIR / "nginx" / "conf.d"
# compose 文件已由 docker-compose.yml 改名为 compose.yml（2776e46）
COMPOSE_FILE = settings.BASE_DIR / "compose.yml"
# 数据库后端模板（只被 compose.yml 的 db extends，不当 -f 传）
COMPOSE_DB_FILE = settings.BASE_DIR / "compose.db.yml"


def _env_file(name: str) -> str:
    """读按层拆分的 env 文件做契约断言。

    `envs/*.env` 是部署本地实例、**不入库**（见 envs/README.md），fresh clone 里只有
    `envs/example/*.env` 模板——模板是变量清单的契约源头，实例是它的部署副本。
    所以实例优先（部署副本校验实际注入容器的文件），没有实例就校验入库模板。
    """
    path = settings.BASE_DIR / "envs" / name
    if not path.exists():
        path = settings.BASE_DIR / "envs" / "example" / name
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("conf_name", ["netops.conf", "netops-ssl.conf.disabled"])
def test_nginx_forwards_host_with_port(conf_name):
    """Host / X-Forwarded-Host 必须是 $http_host（原样含端口），不能用 $host。"""
    text = (NGINX_CONF_DIR / conf_name).read_text(encoding="utf-8")
    headers = re.findall(r"proxy_set_header\s+(Host|X-Forwarded-Host)\s+(\S+);", text)

    assert headers, f"{conf_name} 里没有找到 Host 透传"
    for header, value in headers:
        assert value == "$http_host", f"{conf_name}: {header} 用了 {value}，会把端口丢掉"


@pytest.mark.parametrize("conf_name", ["netops.conf", "netops-ssl.conf.disabled"])
def test_nginx_proxies_mcp_without_buffering(conf_name):
    """`/mcp` 必须有独立 location，且关缓冲、关 gzip、读/发超时到小时级。

    三种漏配各自的表现完全不同，都不好从现象定位：
    - 少这条 location → `/mcp` 落到 SPA 兜底返回 `index.html`（客户端以为「被路由守卫拦住」）；
    - 开了 `proxy_buffering` → SSE 事件攒在 nginx 缓冲区，工具调用一直 pending；
    - 用继承来的 300s 超时 → 长连接中途被掐断（MCP 会话小时级）。
    """
    text = (NGINX_CONF_DIR / conf_name).read_text(encoding="utf-8")
    match = re.search(r"location\s+/mcp\s*\{([^}]*)\}", text)
    assert match, f"{conf_name} 缺少 location /mcp"
    # 空白不固定（有的配置对齐成多列），归一化后再断言
    block = " ".join(match.group(1).split())

    assert "proxy_pass http://$netops_upstream;" in block
    assert "proxy_buffering off;" in block
    assert "gzip off;" in block
    assert "proxy_read_timeout 3600s;" in block
    assert "proxy_send_timeout 3600s;" in block


@pytest.mark.django_db
def test_csrf_origin_is_trusted_only_when_host_carries_port(caplog):
    """Host 带端口时同源 Origin 通过校验；Host 不带端口时同一个 Origin 被拒。

    `enforce_csrf_checks=True` 必须显式打开——测试客户端默认**关掉** CSRF 校验。
    失败原因断言在**日志**上：那是 `django.security.csrf` 汇报的地方（容器里看到的就是
    这一行），而响应体只在 DEBUG=True 时才带上原因，测试期间 Django 强制 DEBUG=False。
    """
    client = Client(enforce_csrf_checks=True)
    post = {"username": "x", "password": "y"}

    with caplog.at_level(logging.WARNING, logger="django.security.csrf"):
        client.post("/admin/login/", post, HTTP_HOST="localhost:8000", HTTP_ORIGIN="http://localhost:8000")
    assert "CSRF cookie not set" in caplog.text  # 没带 cookie 本来就该 403
    assert "Origin checking failed" not in caplog.text  # 但失败原因**不是** Origin

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="django.security.csrf"):
        client.post("/admin/login/", post, HTTP_HOST="localhost", HTTP_ORIGIN="http://localhost:8000")
    assert "Origin checking failed - http://localhost:8000" in caplog.text


def test_app_and_worker_share_the_django_runtime_env_file():
    """`DJANGO_CSRF_TRUSTED_ORIGINS` 等 Django 运行时变量在 `envs/common.env` 里，
    由 compose 给每个跑 Django/celery 的服务**各注入一次**——有的拿不到就会行为不一致
    （celery 也跑同一份 Django settings）。

    环境变量按「谁读」分三处（`.env` 给 compose 插值、`envs/*.env` 给容器、`envs/secrets/*`
    给凭据），所以这条契约现在守的是「文件内容 + 所有运行时服务都注入它」，而不是锚点。

    当前注入方：db（compose.db.yml 的两个模板，postgres 镜像读 DB_NAME）+
    app / worker（celery 双队列）/ consumer（访问流单写者消费者）/ beat（大屏链路缓存调度）
    ——新增服务时这个计数要跟着加。
    """
    compose = COMPOSE_FILE.read_text(encoding="utf-8")
    db_templates = COMPOSE_DB_FILE.read_text(encoding="utf-8")
    common_env = _env_file("common.env")

    assert "DJANGO_CSRF_TRUSTED_ORIGINS=" in common_env
    # 四个应用进程在本体文件里；db 的两份模板各自注入一次
    assert compose.count("- envs/common.env") == 4
    assert db_templates.count("- envs/common.env") == 2


def test_each_service_only_gets_its_own_env_file():
    """按层拆分的 env_file 不许串味：gunicorn 的旋钮不该进 worker，celery 的不该进 app。"""
    compose = COMPOSE_FILE.read_text(encoding="utf-8")

    assert _env_file("gunicorn.env").count("GUNICORN_WORKERS=") == 1
    assert _env_file("celery.env").count("CELERY_LOGLEVEL=") == 1

    app_block = compose.split("  worker:")[0]
    # worker 块切到下一个服务为止：后面还有 consumer（访问流单写者消费者），
    # 跨着切会让「串味」断言被别的服务满足（假绿）
    worker_block = compose.split("  worker:")[1].split("  consumer:")[0]
    assert "- envs/gunicorn.env" in app_block
    assert "- envs/celery.env" not in app_block
    assert "- envs/celery.env" in worker_block
    assert "- envs/gunicorn.env" not in worker_block
    # 两个服务共用 common.env（Django 运行时）与 container.env（容器差异层，排最后）
    assert "- envs/common.env" in app_block
    assert "- envs/common.env" in worker_block
    assert "- envs/container.env" in app_block
    assert "- envs/container.env" in worker_block
    # db 由 extends 引入，env_file 写在 compose.db.yml 的模板里——两个后端都必须只读
    # 共享层 + 容器差异层，不能把 gunicorn / celery 的服务级旋钮带进数据库容器
    db_templates = COMPOSE_DB_FILE.read_text(encoding="utf-8")
    for service_key in ("  postgresql:", "  mysql:"):
        db_block = db_templates.split(service_key)[1].split("\n\n")[0]
        assert "- envs/common.env" in db_block, service_key
        assert "- envs/container.env" in db_block, service_key
        assert "- envs/gunicorn.env" not in db_block, service_key
        assert "- envs/celery.env" not in db_block, service_key


def test_db_credentials_come_from_secrets_not_plaintext_env():
    """数据库用户名/密码必须走 secrets：env 文件里只出现指向 /run/secrets/* 的 `*_FILE`，
    compose 里只出现 secrets 声明与挂载，任何地方都没有明文凭据。

    环境变量在 `docker inspect`、`/proc/1/environ` 里是明文，secret 文件只有挂它的容器看得到。
    """
    compose = COMPOSE_FILE.read_text(encoding="utf-8")

    # 容器差异层把凭据指向 /run/secrets/*（db 与 app/worker 共用这一层）
    container_env = _env_file("container.env")
    assert "DB_USER_FILE=/run/secrets/db_user" in container_env
    assert "DB_PASSWORD_FILE=/run/secrets/db_password" in container_env

    # compose 声明了这两个 secret，并挂给全部需要数据库的服务：
    # consumer 只拿数据库凭据（*db-secrets），app / worker / beat 拿 *app-secrets
    # （数据库凭据 + 阿里云 API 凭据的超集）——新增服务时跟着加；
    # db 本身由 extends 引入，凭据在 compose.db.yml 的模板里显式列出（锚点不能跨文件）
    assert "file: ${DB_USER_SECRET_FILE:-./envs/secrets/db_user}" in compose
    assert "file: ${DB_PASSWORD_SECRET_FILE:-./envs/secrets/db_password}" in compose
    assert compose.count("secrets: *db-secrets") == 1
    assert compose.count("secrets: *app-secrets") == 3
    # 两个锚点都必须包含数据库凭据（app-secrets 是超集，漏掉就是凭据缺失）
    for anchor in ("x-secrets: &db-secrets", "x-app-secrets: &app-secrets"):
        block = compose.split(anchor)[1].split("\n\n")[0]
        assert "- db_user" in block and "- db_password" in block, anchor

    # 两个数据库模板都要拿到凭据：PG 用 user+password，MySQL 的用户名走环境变量、只挂 password
    db_templates = COMPOSE_DB_FILE.read_text(encoding="utf-8")
    pg_block = db_templates.split("  postgresql:")[1].split("\n\n")[0]
    mysql_block = db_templates.split("  mysql:")[1]
    assert "- db_user" in pg_block and "- db_password" in pg_block
    assert "MYSQL_PASSWORD_FILE: /run/secrets/db_password" in mysql_block
    assert "- db_password" in mysql_block

    # 不再有从 .env 插值的明文凭据，也没有直接写死的明文变量
    assert "${DB_PASSWORD:-" not in compose
    assert "${DB_USER:-" not in compose
    assert "\nDB_PASSWORD:" not in compose
    assert "\nDB_USER:" not in compose


def test_env_or_file_prefers_the_secret_file(tmp_path, monkeypatch):
    """`_env_or_file`：`*_FILE` > 环境变量 > 默认值，且文件内容去掉末尾换行。

    末尾换行必须去掉——postgres 官方 entrypoint 的 `$(cat file)` 也是这个行为，
    两边不一致会变成「密码多一个换行」的诡异连不上。
    """
    from netops import settings as project_settings

    secret = tmp_path / "db_password"
    secret.write_text("s3cret\n", encoding="utf-8")

    monkeypatch.setenv("DB_PASSWORD", "plain")
    monkeypatch.setenv("DB_PASSWORD_FILE", str(secret))
    assert project_settings._env_or_file("DB_PASSWORD", "default") == "s3cret"

    monkeypatch.delenv("DB_PASSWORD_FILE")
    assert project_settings._env_or_file("DB_PASSWORD", "default") == "plain"

    monkeypatch.delenv("DB_PASSWORD")
    assert project_settings._env_or_file("DB_PASSWORD", "default") == "default"


def test_env_or_file_resolves_relative_path_against_base_dir(monkeypatch):
    """host.env 里的相对 `*_FILE` 按 BASE_DIR 解析——宿主与容器共用同一份密钥文件。

    容器内是绝对路径 /run/secrets/*，不受影响；宿主在 envs/host.env 里写
    envs/secrets/…（相对路径）即可读同一份 envs/secrets/*，不用再 export 明文。
    """
    from netops import settings as project_settings

    secret = project_settings.BASE_DIR / "tmp" / "pytest-relative-secret"
    secret.parent.mkdir(exist_ok=True)
    secret.write_text("s3cret\n", encoding="utf-8")
    try:
        monkeypatch.setenv("DB_PASSWORD_FILE", "tmp/pytest-relative-secret")
        assert project_settings._env_or_file("DB_PASSWORD", "default") == "s3cret"
    finally:
        secret.unlink(missing_ok=True)


def test_env_or_file_fails_loudly_on_unreadable_secret(tmp_path, monkeypatch):
    """挂了 secret 但读不出来要直接报错，不能静默回退到默认密码。"""
    from django.core.exceptions import ImproperlyConfigured

    from netops import settings as project_settings

    monkeypatch.setenv("DB_PASSWORD_FILE", str(tmp_path / "missing"))
    with pytest.raises(ImproperlyConfigured):
        project_settings._env_or_file("DB_PASSWORD", "default")


def test_env_list_parsing(monkeypatch):
    """`_env_list`：逗号分隔、去空白、丢空项，未设置时用 default。"""
    from netops import settings as project_settings

    monkeypatch.delenv("DJANGO_CSRF_TRUSTED_ORIGINS", raising=False)
    assert project_settings._env_list("DJANGO_CSRF_TRUSTED_ORIGINS") == []

    monkeypatch.setenv("DJANGO_CSRF_TRUSTED_ORIGINS", " https://a.example.com , ,http://localhost:8000 ")
    assert project_settings._env_list("DJANGO_CSRF_TRUSTED_ORIGINS") == [
        "https://a.example.com",
        "http://localhost:8000",
    ]

    monkeypatch.delenv("DJANGO_ALLOWED_HOSTS", raising=False)
    assert project_settings._env_list("DJANGO_ALLOWED_HOSTS", "*") == ["*"]
