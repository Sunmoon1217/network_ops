from django.urls import path

from . import configs, imports, parsers

urlpatterns = [
    # 配置仓库：前端 api/config.ts、api/devices.ts 已在调用，此前未注册路由（404）
    path("configs/git-content/", configs.git_content, name="config-git-content"),
    path("configs/git-diff/", configs.git_diff, name="config-git-diff"),
    path("configs/history/", configs.config_history, name="config-history"),
    path("configs/devices/", configs.config_devices, name="config-devices"),
    # Excel 批量导入：URL 前缀与 name 都沿用拆分前（前端零改动）。assets.api.urls 里
    # 已无这两个路由，不会撞车；即便将来重复，Django 也是按 include 顺序命中即止。
    path("assets/import-devices/", imports.import_excel, name="import-devices"),
    path("assets/import-template/", imports.import_template, name="import-template"),
    # 解析器与 TTP 模板
    path("parsers/", parsers.parser_list, name="parser-list"),
    path("parsers/mapping/", parsers.parser_mapping, name="parser-mapping"),
    path("parsers/templates/", parsers.parser_template_list, name="parser-template-list"),
    path("parsers/templates/<str:name>/", parsers.parser_template_detail, name="parser-template-detail"),
    path("parsers/templates/<str:name>/update/", parsers.parser_template_update, name="parser-template-update"),
    # 路径追踪 / 资产分析 / 访问流已拆去 analysis.api.urls（URL 前缀不变，见 netops/urls.py）
]
