"""反向代理与 Django 的接口契约（nginx 配置 + compose 环境变量）。

守的是一条**实测踩过的坑**：nginx 用 `proxy_set_header Host $host` 时端口会被丢掉，
宿主机映射到非标准端口（`NGINX_PORT=8000`）后，Django 的 `request.get_host()` 得到
`localhost`，而浏览器的 Origin 是 `http://localhost:8000`——CSRF 的 Origin 校验只认
「当前 host」与 `CSRF_TRUSTED_ORIGINS`，于是登录直接 403：

    Forbidden (Origin checking failed - http://localhost:8000 does not match any
    trusted origins.): /admin/login/

同样的请求只把 Host 从 `localhost:8000` 换成 `localhost`，失败原因就变成
「CSRF cookie not set」——即 Origin 校验已通过。这三条测试分别锁住：nginx 侧必须
透传带端口的 Host、Django 侧「Host 带端口则同源 Origin 可信」的规则、以及 compose
把 `DJANGO_CSRF_TRUSTED_ORIGINS` 传进 app/worker 两个容器。
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


def test_compose_passes_csrf_origins_to_app_and_worker():
    """DJANGO_CSRF_TRUSTED_ORIGINS 要在共享锚点里，app 与 worker 才都会拿到。"""
    text = COMPOSE_FILE.read_text(encoding="utf-8")

    assert "DJANGO_CSRF_TRUSTED_ORIGINS: ${DJANGO_CSRF_TRUSTED_ORIGINS:-}" in text
    # 锚点定义 1 次 + app / worker 各引用 1 次
    assert text.count("*app-environment") == 2


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
