"""双入口静态托管契约：nginx 直出与 Django 托管都必须单独处理大屏。

`index.html` / `dashboard.html` 是 Vite 的两个入口，共用同一份 main chunk，靠页面里的
`#app` / `#dashboard` 决定挂载哪个应用。只要大屏请求被 SPA 兜底换成主站 index.html，
页面里就没有 `#dashboard`，大屏表现为空白（甚至被主站路由守卫弹回登录）。

两条链路各自都要认得 dashboard.html：nginx 的 `try_files ... /index.html` 只兜主站，
Django 的 `vue_index` 兜底也只回主站，谁都不能把大屏请求交给它。
"""

import re

import pytest
from django.conf import settings
from django.test import Client
from django.urls import resolve

from netops import views

NGINX_CONF = settings.BASE_DIR / "nginx" / "conf.d" / "netops.conf"


@pytest.mark.django_db
def test_django_serves_each_entry_from_its_own_html(tmp_path, monkeypatch):
    """两个入口各返回自己的 html；SPA 兜底仍然只回主站 index.html。"""
    (tmp_path / "index.html").write_text('<div id="app"></div>', encoding="utf-8")
    (tmp_path / "dashboard.html").write_text('<div id="dashboard"></div>', encoding="utf-8")
    monkeypatch.setattr(views, "FRONTEND", tmp_path)

    for path in ("/dashboard.html", "/dashboard", "/dashboard/"):
        assert resolve(path).func is views.vue_dashboard

    client = Client()
    for path in ("/dashboard.html", "/dashboard", "/dashboard/"):
        res = client.get(path)
        assert res.status_code == 200
        assert res.headers["Content-Type"].startswith("text/html")
        assert b'id="dashboard"' in res.content

    for path in ("/", "/devices"):
        assert b'id="app"' in client.get(path).content


@pytest.mark.django_db
def test_django_dashboard_entry_missing_is_not_replaced_by_index(tmp_path, monkeypatch):
    """大屏 html 没构建时明确 404，不能悄悄回退到主站 index.html。"""
    (tmp_path / "index.html").write_text('<div id="app"></div>', encoding="utf-8")
    monkeypatch.setattr(views, "FRONTEND", tmp_path)

    res = Client().get("/dashboard.html")
    assert res.status_code == 404
    assert b'id="app"' not in res.content


def test_nginx_routes_dashboard_entry_separately():
    """大屏有独立 location（含友好 URL 与 no-cache），主站兜底不被改写。"""
    text = NGINX_CONF.read_text(encoding="utf-8")

    assert "location = /dashboard.html {" in text
    assert "location = /dashboard {" in text
    assert "location = /dashboard/ {" in text
    assert text.count("try_files /dashboard.html =404;") == 2

    dashboard_block = text.split("location = /dashboard.html {")[1].split("}")[0]
    assert "no-cache, no-store, must-revalidate" in dashboard_block
    assert "try_files $uri $uri/ /index.html;" in text


@pytest.mark.parametrize("dockerfile_name", ["dockerfile", "dockerfile.code"])
def test_image_build_rejects_dist_without_dashboard_entry(dockerfile_name):
    """镜像构建要校验两个入口都在：只 COPY 了 index.html 的旧 dist 会让大屏 404。"""
    text = (settings.BASE_DIR / dockerfile_name).read_text(encoding="utf-8")

    assert re.search(r"\[ ! -f \S*/dashboard\.html \]", text)
