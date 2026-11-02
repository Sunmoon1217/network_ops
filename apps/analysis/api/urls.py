"""分析域的 API：路径追踪 / 路由采集 / DNS 查询 / 互联网资产分析 / 关联链聚合 /
设备组配置合并（GSLB 集群、LTM 主备）/ 访问流。

URL 前缀保持拆分前的原样（``/api/trace/...``、``/api/internet-analysis/...``、
``/api/access-flows/...``），前端 ``api/`` 与 ``views/tools/`` 无需任何改动——
路由跟着 view 走，不跟 app 走。设备组合并接口另开 ``/api/analysis/`` 前缀：
它换了合并口径（按组合并、device 拼接），不混进旧接口。
"""

from django.urls import path
from rest_framework.routers import SimpleRouter

from . import accessflows, analysis, firewall_groups, gslb_clusters, lb_chain, ltm_groups, monitor, trace

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
    path("lb-chain/slb/export/", lb_chain.ltm_export, name="lb-chain-slb-export"),
    path("lb-chain/gslb/", lb_chain.gtm_chains, name="lb-chain-gslb"),
    path("lb-chain/gslb/facets/", lb_chain.gtm_facets, name="lb-chain-gslb-facets"),
    path("lb-chain/gslb/export/", lb_chain.gtm_export, name="lb-chain-gslb-export"),
    # GSLB 集群分析：同集群多台设备的 GTM 配置逐层合并，device 字段逗号拼接
    path("analysis/gslb-clusters/", gslb_clusters.gslb_clusters, name="gslb-clusters"),
    path("analysis/gslb-clusters/facets/", gslb_clusters.gslb_cluster_facets, name="gslb-clusters-facets"),
    path("analysis/gslb-clusters/export/", gslb_clusters.gslb_cluster_export, name="gslb-clusters-export"),
    # LTM 主备合并：同主备组多台 SLB 的 VS→池→成员逐层合并，device 字段逗号拼接
    path("analysis/ltm-groups/", ltm_groups.ltm_groups, name="ltm-groups"),
    path("analysis/ltm-groups/facets/", ltm_groups.ltm_group_facets, name="ltm-groups-facets"),
    path("analysis/ltm-groups/export/", ltm_groups.ltm_group_export, name="ltm-groups-export"),
    # 防火墙主备合并：同主备组多台防火墙的策略 / NAT 合并，policy_id 冲突取主机名第一台
    path("analysis/firewall-groups/policies/", firewall_groups.firewall_policies, name="firewall-groups-policies"),
    path("analysis/firewall-groups/nat-rules/", firewall_groups.firewall_nat_rules, name="firewall-groups-nat-rules"),
    path("analysis/firewall-groups/facets/", firewall_groups.firewall_group_facets, name="firewall-groups-facets"),
    # 队列积压巡检（celery 队列 / 访问流 Stream / 消费者心跳）：只读，Home 页卡片轮询
    path("analysis/queue-status/", monitor.queue_status, name="queue-status"),
    # 运行监控（只读）：Redis 服务状态（INFO）/ Celery worker 与任务（inspect），运行监控页轮询
    path("analysis/redis-status/", monitor.redis_status, name="redis-status"),
    path("analysis/celery-status/", monitor.celery_status, name="celery-status"),
]

urlpatterns += router.urls
