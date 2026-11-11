"""API 文档（OpenAPI 3）的路由与访问契约。

挂在 /api/schema/ 下而不是 /api/docs/：后者是 docs 业务域（表格编辑 / 文档转换）的前缀。
/api/schema/ 是浏览器入口（302 → Swagger UI），描述文件在 /api/schema/openapi.yaml：
两个 UI 靠 name="schema" 反解取数，这条不能断，否则 UI 会拉到重定向后的 HTML。
四条路由都在 /api/ 下 → nginx 的 /api/ 代理与 SPA_EXCLUDE_PREFIXES 都不用改
（保留前缀的行为由 tests/test_urls.py 守）。
"""

import pytest
from django.test import Client
from django.urls import resolve, reverse
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from netops import views

SCHEMA_PATH = "/api/schema/openapi.yaml"


@pytest.mark.parametrize(
    ("path", "view_class"),
    [
        (SCHEMA_PATH, SpectacularAPIView),
        ("/api/schema/swagger-ui/", SpectacularSwaggerView),
        ("/api/schema/redoc/", SpectacularRedocView),
    ],
)
def test_api_docs_routes_bound_to_expected_view(path, view_class):
    assert resolve(path).func.cls is view_class


def test_schema_url_name_points_to_file():
    assert reverse("schema") == SCHEMA_PATH


def test_schema_root_redirects_to_swagger_ui():
    response = Client().get("/api/schema/")
    assert response.status_code == 302
    assert response["Location"] == reverse("swagger-ui")


def test_schema_root_redirect_is_followable():
    response = Client().get("/api/schema/", follow=True)
    assert response.status_code == 200
    assert len(response.redirect_chain) == 1


def test_api_docs_route_not_claimed_by_spa():
    assert resolve("/api/schema/").func.view_class is RedirectView
    assert resolve("/api/schema/").func is not views.vue_index


@pytest.mark.parametrize("path", ["/api/schema/", "/api/schema/swagger-ui/", "/api/schema/redoc/"])
def test_api_docs_pages_are_reachable(path):
    assert Client().get(path, follow=True).status_code == 200


def test_schema_is_openapi():
    assert b"openapi" in Client().get(SCHEMA_PATH).content.lower()


@pytest.mark.parametrize("path", ["/api/schema/swagger-ui/", "/api/schema/redoc/"])
def test_ui_fetches_schema_file_not_redirect(path):
    assert Client().get(path).data["schema_url"] == SCHEMA_PATH


def test_business_docs_routes_unchanged():
    assert resolve("/api/docs/spreadsheets/").url_name == "spreadsheet-list"
