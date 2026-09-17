"""URL 路由分层测试。

重点在 SPA 兜底正则：它必须排除 admin / api / static / assets / media，
而且**带不带尾斜杠都要排除**。早先只写了 "admin/"，于是不带尾斜杠的 /admin
不以前者开头，被兜底交给 Vue，返回了前端页面；同时 path("admin/") 也匹配不上
它，Django 的 APPEND_SLASH 因为这里没返回 404 而始终不生效。

注意：Django 传给正则的 path **不含前导斜杠**，所以排除项写的是 "admin" 而非
"/admin"；断言时要用 resolve() 走真实链路，别手写正则去 match("/admin")。
"""

import pytest
from django.test import Client
from django.urls import Resolver404, resolve

RESERVED_WITHOUT_SLASH = ("/admin", "/api", "/static")


@pytest.mark.django_db
def test_admin_without_trailing_slash_goes_to_django():
    """不带尾斜杠的 /admin 应由 Django 补斜杠，而不是返回 SPA 页面"""
    res = Client().get("/admin")

    assert res.status_code == 301
    assert res.headers["Location"] == "/admin/"


@pytest.mark.django_db
def test_admin_with_trailing_slash_reaches_login():
    """/admin/ 跳登录页，是 Django admin 的正常入口"""
    res = Client().get("/admin/")

    assert res.status_code == 302
    assert "/admin/login/" in res.headers["Location"]


@pytest.mark.parametrize("path", RESERVED_WITHOUT_SLASH)
def test_reserved_prefixes_are_not_claimed_by_spa(path):
    """保留前缀不该被 SPA 兜底认领（认领了就不会有 404，APPEND_SLASH 也就失效）"""
    with pytest.raises(Resolver404):
        resolve(path)


def test_frontend_routes_still_fall_through_to_spa():
    """只是前缀相同的路径（/adminfoo）以及普通前端路由，仍交给 Vue"""
    from netops import views

    assert resolve("/adminfoo").func is views.vue_index
    assert resolve("/some/spa/route").func is views.vue_index
