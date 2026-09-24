"""分析域的 API：路径追踪 / 路由采集 / DNS 查询 / 互联网资产分析 / 关联链聚合 / 访问流。

URL 前缀保持拆分前的原样（``/api/trace/...``、``/api/internet-analysis/...``、
``/api/access-flows/...``），前端 ``api/`` 与 ``views/tools/`` 无需任何改动——
路由跟着 view 走，不跟 app 走。
"""

from django.urls import path
from rest_framework.routers import SimpleRouter

from . import accessflows, analysis, lb_chain, trace

router = SimpleRouter()
# 访问流（2026-09 随模型由 ingest 迁入）：URL 不变，前端零改动
router.register("access-flows", accessflows.AccessFlowViewSet, basename="access-flow")

urlpatterns = [
    path("trace/", trace.path_trace, name="path-trace"),
    path("trace/route-collect/", trace.route_collect, name="route-collect"),
    path("trace/route-collect-raw/", trace.route_collect_raw, name="route-collect-raw"),
    path("trace/routes/", trace.route_list, name="route-list"),
    path("trace/dns-query/", trace.dns_query, name="dns-query"),
    # 互联网资产分析：结果走缓存，只有 analyze 才真正触发计算
    path("internet-analysis/", analysis.internet_analysis, name="internet-analysis"),
    path("internet-analysis/analyze/", analysis.internet_analysis_run, name="internet-analysis-run"),
    path("internet-analysis/export/", analysis.internet_analysis_export, name="internet-analysis-export"),
    # 关联链聚合：VS→池→成员 / WideIP→池→GTM虚拟服务器，一行返回整链
    path("lb-chain/slb/", lb_chain.ltm_chains, name="lb-chain-slb"),
    path("lb-chain/gslb/", lb_chain.gtm_chains, name="lb-chain-gslb"),
    path("lb-chain/gslb/facets/", lb_chain.gtm_facets, name="lb-chain-gslb-facets"),
]

urlpatterns += router.urls
