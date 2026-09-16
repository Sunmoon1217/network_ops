from django.urls import path

from . import configs, parsers, trace

urlpatterns = [
    path("trace/", trace.path_trace, name="path-trace"),
    path("trace/route-collect/", trace.route_collect, name="route-collect"),
    path("trace/route-collect-raw/", trace.route_collect_raw, name="route-collect-raw"),
    path("trace/routes/", trace.route_list, name="route-list"),
    path("trace/dns-query/", trace.dns_query, name="dns-query"),
    # 配置仓库：前端 api/config.ts、api/devices.ts 已在调用，此前未注册路由（404）
    path("configs/git-content/", configs.git_content, name="config-git-content"),
    path("configs/git-diff/", configs.git_diff, name="config-git-diff"),
    path("configs/history/", configs.config_history, name="config-history"),
    path("configs/devices/", configs.config_devices, name="config-devices"),
    # 解析器与 TTP 模板
    path("parsers/", parsers.parser_list, name="parser-list"),
    path("parsers/mapping/", parsers.parser_mapping, name="parser-mapping"),
    path("parsers/templates/", parsers.parser_template_list, name="parser-template-list"),
    path("parsers/templates/<str:name>/", parsers.parser_template_detail, name="parser-template-detail"),
    path("parsers/templates/<str:name>/update/", parsers.parser_template_update, name="parser-template-update"),
]
