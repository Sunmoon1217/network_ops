from django.urls import include, path

from . import configs, imports, parsers

# 采集域一个前缀收全部：配置仓库读取（config-repo/）、Excel 批量导入（import-*）、
# 解析器（parsers/）。此前这四类分散在 /api/configs/、/api/assets/、/api/parsers/ 三处，
# 与实际归属对不上；路由表见 handbook/api.md。
urlpatterns = [
    path(
        "ingest/",
        include(
            [
                path("config-repo/content/", configs.git_content, name="config-git-content"),
                path("config-repo/diff/", configs.git_diff, name="config-git-diff"),
                path("config-repo/history/", configs.config_history, name="config-history"),
                path("config-repo/devices/", configs.config_devices, name="config-devices"),
                path("import-devices/", imports.import_excel, name="import-devices"),
                path("import-template/", imports.import_template, name="import-template"),
                path("parsers/", parsers.parser_list, name="parser-list"),
                path("parsers/mapping/", parsers.parser_mapping, name="parser-mapping"),
                path("parsers/templates/", parsers.parser_template_list, name="parser-template-list"),
                path("parsers/templates/<str:name>/", parsers.parser_template_detail, name="parser-template-detail"),
                path("parsers/templates/<str:name>/update/", parsers.parser_template_update, name="parser-template-update"),
            ]
        ),
    ),
]
