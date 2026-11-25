"""分析域的 API：路径追踪 / 路由采集 / DNS 查询 / 互联网资产分析 / 关联链聚合 /
设备组配置合并（GSLB 集群、LTM 主备）/ 访问流 / 运行监控 / 资产总览。

全部挂在 ``/api/analysis/`` 下，大屏供数是唯一的独立面（``/api/dashboard/``，免认证、
契约不同）。路由表见 handbook/api.md。
"""

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import accessflows, analysis, dashboard, lb_chain, overview, runtime, trace
from .groups import firewall, gslb, ltm

router = SimpleRouter()
# 访问流（2026-09 随模型由 ingest 迁入）：只读，列表即策略展开结果
router.register("access-flows", accessflows.AccessFlowViewSet, basename="access-flow")

urlpatterns = [
    path(
        "analysis/",
        include(
            [
                # 资产总览（Home 页）：跨 assets + configs 的只读聚合
                path("overview/", overview.assets_overview, name="assets-overview"),
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
                path("lb-chain/slb/export/", lb_chain.ltm_export, name="lb-chain-slb-export"),
                path("lb-chain/gslb/", lb_chain.gtm_chains, name="lb-chain-gslb"),
                path("lb-chain/gslb/facets/", lb_chain.gtm_facets, name="lb-chain-gslb-facets"),
                path("lb-chain/gslb/export/", lb_chain.gtm_export, name="lb-chain-gslb-export"),
                # GSLB 集群分析：同集群多台设备的 GTM 配置逐层合并，device 字段逗号拼接
                path("gslb-clusters/", gslb.gslb_clusters, name="gslb-clusters"),
                path("gslb-clusters/facets/", gslb.gslb_cluster_facets, name="gslb-clusters-facets"),
                path("gslb-clusters/export/", gslb.gslb_cluster_export, name="gslb-clusters-export"),
                # LTM 主备合并：同主备组多台 SLB 的 VS→池→成员逐层合并，device 字段逗号拼接
                path("ltm-groups/", ltm.ltm_groups, name="ltm-groups"),
                path("ltm-groups/facets/", ltm.ltm_group_facets, name="ltm-groups-facets"),
                path("ltm-groups/export/", ltm.ltm_group_export, name="ltm-groups-export"),
                # 防火墙主备合并：同主备组多台防火墙的策略 / NAT 合并，policy_id 冲突取主机名第一台
                path("firewall-groups/policies/", firewall.firewall_policies, name="firewall-groups-policies"),
                path("firewall-groups/nat-rules/", firewall.firewall_nat_rules, name="firewall-groups-nat-rules"),
                path("firewall-groups/facets/", firewall.firewall_group_facets, name="firewall-groups-facets"),
                # 队列积压巡检（celery 队列 / 访问流 Stream / 消费者心跳）：只读，Home 页卡片轮询
                path("queue-status/", runtime.queue_status, name="queue-status"),
                # 运行监控（只读）：Redis 服务状态（INFO）/ Celery worker 与任务（inspect），运行监控页轮询
                path("redis-status/", runtime.redis_status, name="redis-status"),
                path("celery-status/", runtime.celery_status, name="celery-status"),
            ]
            + router.urls
        ),
    ),
    # 大屏供数（只读、免认证）：无人值守展示页，不依赖登录态；独立契约（{status,message,result}）
    path("dashboard/", dashboard.dashboard, name="dashboard"),
    path("dashboard/cabinets/", dashboard.dashboard_cabinets, name="dashboard-cabinets"),
]
