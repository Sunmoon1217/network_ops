from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path

from . import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("core.api.urls")),
    path("api/", include("assets.api.urls")),
    path("api/", include("ops.api.urls")),
    # 分析域：URL 前缀沿用拆分前的 /api/trace/、/api/internet-analysis/（前端零改动）
    path("api/", include("analysis.api.urls")),
    path("favicon.ico", views.favicon),
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
