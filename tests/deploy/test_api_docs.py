"""API 文档（OpenAPI 3）的路由与访问契约。

挂在 /api/schema/ 而不是 /api/docs/：后者是 docs 业务域（表格编辑 / 文档转换）的前缀。
三个路由都在 /api/ 下 → nginx 的 /api/ 代理与 SPA_EXCLUDE_PREFIXES 都不用改
（保留前缀的行为由 tests/test_urls.py 守）。
"""

import pytest
from django.test import Client
from django.urls import resolve
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from netops import views


@pytest.mark.parametrize(
    ("path", "view_class"),
    [
        ("/api/schema/", SpectacularAPIView),
        ("/api/schema/swagger-ui/", SpectacularSwaggerView),
        ("/api/schema/redoc/", SpectacularRedocView),
    ],
)
def test_api_docs_routes_bound_to_expected_view(path, view_class):
    assert resolve(path).func.cls is view_class


def test_api_docs_route_not_claimed_by_spa():
    assert resolve("/api/schema/").func is not views.vue_index


@pytest.mark.parametrize("path", ["/api/schema/", "/api/schema/swagger-ui/", "/api/schema/redoc/"])
def test_api_docs_pages_are_reachable(path):
    assert Client().get(path).status_code == 200


def test_schema_is_openapi():
    assert b"openapi" in Client().get("/api/schema/").content.lower()


def test_business_docs_routes_unchanged():
    assert resolve("/api/docs/spreadsheets/").url_name == "spreadsheet-list"
