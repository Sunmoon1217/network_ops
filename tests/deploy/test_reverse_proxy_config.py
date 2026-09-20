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
`DJANGO_CSRF_TRUSTED_ORIGINS`（在 `env/app.env` 里）注入 app/worker 两个容器、
按服务拆分的 `env_file` 不许串味、以及数据库凭据只从 secrets 读。
"""

import logging
import re

import pytest
from django.conf import settings
from django.test import Client

NGINX_CONF_DIR = settings.BASE_DIR / "nginx" / "conf.d"
COMPOSE_FILE = settings.BASE_DIR / "docker-compose.yml"


@pytest.mark.parametrize("conf_name", ["netops.conf", "netops-ssl.conf.disabled"])
def test_nginx_forwards_host_with_port(conf_name):
    """Host / X-Forwarded-Host 必须是 $http_host（原样含端口），不能用 $host。"""
    text = (NGINX_CONF_DIR / conf_name).read_text(encoding="utf-8")
    headers = re.findall(r"proxy_set_header\s+(Host|X-Forwarded-Host)\s+(\S+);", text)

    assert headers, f"{conf_name} 里没有找到 Host 透传"
    for header, value in headers:
        assert value == "$http_host", f"{conf_name}: {header} 用了 {value}，会把端口丢掉"


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
    """`DJANGO_CSRF_TRUSTED_ORIGINS` 等 Django 运行时变量在 `env/app.env` 里，
    由 compose 给 app 与 worker **各注入一次**——两边都拿不到就会行为不一致
    （celery 也跑同一份 Django settings）。

    环境变量按「谁读」分三处（`.env` 给 compose 插值、`env/*.env` 给容器、`env/secrets/*`
    给凭据），所以这条契约现在守的是「文件内容 + 两个服务都注入它」，而不是锚点。
    """
    compose = COMPOSE_FILE.read_text(encoding="utf-8")
    app_env = (settings.BASE_DIR / "env" / "app.env").read_text(encoding="utf-8")

    assert "DJANGO_CSRF_TRUSTED_ORIGINS=" in app_env
    # app 与 worker 各注入一次
    assert compose.count("- env/app.env") == 2


def test_each_service_only_gets_its_own_env_file():
    """按服务拆分的 env_file 不许串味：gunicorn 的旋钮不该进 worker，celery 的不该进 app。"""
    compose = COMPOSE_FILE.read_text(encoding="utf-8")
    env_dir = settings.BASE_DIR / "env"

    assert (env_dir / "gunicorn.env").read_text(encoding="utf-8").count("GUNICORN_WORKERS=") == 1
    assert (env_dir / "celery.env").read_text(encoding="utf-8").count("CELERY_LOGLEVEL=") == 1

    app_block, worker_block = compose.split("  worker:")[0], compose.split("  worker:")[1]
    assert "- env/gunicorn.env" in app_block
    assert "- env/celery.env" not in app_block
    assert "- env/celery.env" in worker_block
    assert "- env/gunicorn.env" not in worker_block
    # 两个服务共用 app.env（Django 运行时）
    assert "- env/app.env" in app_block
    assert "- env/app.env" in worker_block
    # db 只读自己的那份
    db_block = compose.split("  db:")[1].split("  redis:")[0]
    assert "- env/db.env" in db_block
    assert "- env/app.env" not in db_block


def test_db_credentials_come_from_secrets_not_plaintext_env():
    """数据库用户名/密码必须走 secrets：env 文件里只出现指向 /run/secrets/* 的 `*_FILE`，
    compose 里只出现 secrets 声明与挂载，任何地方都没有明文凭据。

    环境变量在 `docker inspect`、`/proc/1/environ` 里是明文，secret 文件只有挂它的容器看得到。
    """
    compose = COMPOSE_FILE.read_text(encoding="utf-8")
    env_dir = settings.BASE_DIR / "env"

    # db 与 app/worker 的 env 文件都把凭据指向 /run/secrets/*
    for name in ("db.env", "app.env"):
        text = (env_dir / name).read_text(encoding="utf-8")
        assert "POSTGRES_USER_FILE=/run/secrets/postgres_user" in text
        assert "POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password" in text

    # compose 声明了这两个 secret，并挂给 db / app / worker 三个服务
    assert "file: ${POSTGRES_USER_SECRET_FILE:-./env/secrets/postgres_user}" in compose
    assert "file: ${POSTGRES_PASSWORD_SECRET_FILE:-./env/secrets/postgres_password}" in compose
    assert compose.count("secrets: *db-secrets") == 3

    # 不再有从 .env 插值的明文凭据，也没有直接写死的明文变量
    assert "${POSTGRES_PASSWORD:-" not in compose
    assert "${POSTGRES_USER:-" not in compose
    assert "\nPOSTGRES_PASSWORD:" not in compose
    assert "\nPOSTGRES_USER:" not in compose


def test_env_or_file_prefers_the_secret_file(tmp_path, monkeypatch):
    """`_env_or_file`：`*_FILE` > 环境变量 > 默认值，且文件内容去掉末尾换行。

    末尾换行必须去掉——postgres 官方 entrypoint 的 `$(cat file)` 也是这个行为，
    两边不一致会变成「密码多一个换行」的诡异连不上。
    """
    from netops import settings as project_settings

    secret = tmp_path / "postgres_password"
    secret.write_text("s3cret\n", encoding="utf-8")

    monkeypatch.setenv("POSTGRES_PASSWORD", "plain")
    monkeypatch.setenv("POSTGRES_PASSWORD_FILE", str(secret))
    assert project_settings._env_or_file("POSTGRES_PASSWORD", "default") == "s3cret"

    monkeypatch.delenv("POSTGRES_PASSWORD_FILE")
    assert project_settings._env_or_file("POSTGRES_PASSWORD", "default") == "plain"

    monkeypatch.delenv("POSTGRES_PASSWORD")
    assert project_settings._env_or_file("POSTGRES_PASSWORD", "default") == "default"


def test_env_or_file_fails_loudly_on_unreadable_secret(tmp_path, monkeypatch):
    """挂了 secret 但读不出来要直接报错，不能静默回退到默认密码。"""
    from django.core.exceptions import ImproperlyConfigured

    from netops import settings as project_settings

    monkeypatch.setenv("POSTGRES_PASSWORD_FILE", str(tmp_path / "missing"))
    with pytest.raises(ImproperlyConfigured):
        project_settings._env_or_file("POSTGRES_PASSWORD", "default")


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
