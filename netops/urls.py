from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from . import views

urlpatterns = [
    path("admin/", admin.site.urls),
    # OpenAPI 3 文档：三个路由都在 /api/ 下，nginx 的 /api/ 代理与 SPA_EXCLUDE_PREFIXES 不用改。
    # 不叫 /api/docs/——那是 docs 业务域（表格编辑 / 文档转换）的前缀。
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("api/", include("core.api.urls")),
    path("api/", include("assets.api.urls")),
    path("api/", include("ingest.api.urls")),
    # 分析域：URL 前缀沿用拆分前的 /api/trace/、/api/internet-analysis/（前端零改动）
    path("api/", include("analysis.api.urls")),
    # 文档域（表格编辑 + 文档转换）：/api/docs/
    path("api/", include("docs.api.urls")),
    path("favicon.ico", views.favicon),
    # Vite 双入口：大屏必须单独接管，不能落到下面的 SPA 兜底（那里一律返回主站 index.html）。
    # /dashboard 是友好 URL，与 nginx 的 location = /dashboard 对齐；两个入口共用 /assets/*。
    # 这里不整段排除 dashboard 前缀：大屏没有前端路由，其余子路径仍由主站兜底，
    # 与 nginx 的 try_files 行为保持一致。
    path("dashboard.html", views.vue_dashboard),
    re_path(r"^dashboard/?$", views.vue_dashboard),
    re_path(r"^assets/(?P<path>.*)$", views.serve_frontend_assets),
]

# 交给 Vue 路由兜底时要排除的前缀。
# 注意排除项是「前缀 + (斜杠或结尾)」，这样 /admin 和 /admin/ 都会被排除：
# 若只写 "admin/"，不带尾斜杠的 /admin 不以前者开头，会被 Vue 兜底吃掉，
# 而 path("admin/") 又匹配不上它，Django 的 APPEND_SLASH 也因未返回 404 而不生效。
SPA_EXCLUDE_PREFIXES = ("admin", "api", "static", "assets", "media")

urlpatterns += [
    re_path(r"^(?!(?:%s)(?:/|$)).*$" % "|".join(SPA_EXCLUDE_PREFIXES), views.vue_index),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
