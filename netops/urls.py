from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from . import views

urlpatterns = [
    path("admin/", admin.site.urls),
    # OpenAPI 3 文档：/api/schema/ 是浏览器入口，302 到 Swagger UI；描述文件单独挂在
    # /api/schema/openapi.yaml，name="schema" 不能丢——两个 UI 靠它反解取数，
    # 若把 schema 视图留在 /api/schema/，UI 会拉到重定向后的 HTML 而不是 OpenAPI 文件。
    # 四条路由都在 /api/ 下，nginx 的 /api/ 代理与 SPA_EXCLUDE_PREFIXES 不用改。
    # 不叫 /api/docs/——那是 docs 业务域（表格编辑 / 文档转换）的前缀。
    path("api/schema/", RedirectView.as_view(pattern_name="swagger-ui", permanent=False), name="api-docs"),
    path("api/schema/openapi.yaml", SpectacularAPIView.as_view(), name="schema"),
    path("api/schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # 域名一个顶层前缀：/api/core/、/api/assets/、/api/configs/、/api/ingest/、
    # /api/analysis/（+ 独立的大屏面 /api/dashboard/）、/api/docs/。auth 与 me 留在根下。
    # 归属规则与完整路由表见 handbook/api.md。
    path("api/", include("core.api.urls")),
    path("api/", include("assets.api.urls")),
    path("api/", include("configs.api.urls")),
    path("api/", include("ingest.api.urls")),
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
    # 根路径 302 到大屏（与 nginx 的 location = / 及 vite dev 中间件一致）：
    # 主站入口挪到 /overview，根路径专门留给免认证的大屏。
    # 必须放在下面的 SPA 兜底之前，否则 / 会被 vue_index 吃掉返回主站首页。
    path("", RedirectView.as_view(url="/dashboard", permanent=False), name="root"),
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
