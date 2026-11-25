from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from . import views

urlpatterns = [
    path("admin/", admin.site.urls),
    # OpenAPI 3 文档：/api/schema/ 302 到 Swagger UI；描述文件单独挂，name="schema" 不能丢。
    # 不叫 /api/docs/（那是 docs 业务域）。完整路由与约定见 handbook/api.md。
    path("api/schema/", RedirectView.as_view(pattern_name="swagger-ui", permanent=False), name="api-docs"),
    path("api/schema/openapi.yaml", SpectacularAPIView.as_view(), name="schema"),
    path("api/schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # 各业务域统一挂在 /api/ 下；auth 与 me 留在根下。
    path("api/", include("core.api.urls")),
    path("api/", include("assets.api.urls")),
    path("api/", include("configs.api.urls")),
    path("api/", include("ingest.api.urls")),
    path("api/", include("analysis.api.urls")),
    # 文档域（表格编辑 + 文档转换）：/api/docs/
    path("api/", include("docs.api.urls")),
    path("favicon.ico", views.favicon),
    # 双入口：大屏必须单独接管，不能落到 SPA 兜底（那里只回主站 index.html）。
    # /dashboard 与 nginx 的 location 对齐，两个入口共用 /assets/*。
    path("dashboard.html", views.vue_dashboard),
    re_path(r"^dashboard/?$", views.vue_dashboard),
    re_path(r"^assets/(?P<path>.*)$", views.serve_frontend_assets),
    # 根路径 302 到大屏；主站入口在 /overview。必须排在 SPA 兜底之前。
    path("", RedirectView.as_view(url="/dashboard", permanent=False), name="root"),
]

# 交给 Vue 路由兜底时排除的前缀。排除项按「前缀 + (斜杠或结尾)」匹配，
# 否则不带尾斜杠的 /admin 会被 Vue 兜底吃掉。
SPA_EXCLUDE_PREFIXES = ("admin", "api", "static", "assets", "media")

urlpatterns += [
    re_path(r"^(?!(?:%s)(?:/|$)).*$" % "|".join(SPA_EXCLUDE_PREFIXES), views.vue_index),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
