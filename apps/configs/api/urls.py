"""配置域路由：挂在 ``/api/configs/`` 下，前缀与 app 一一对应。

2026-11 之前这些资源与 assets 共用 ``/api/assets/``（拆分时为了前端零改动），
结果 ``/api/assets/`` 变成三个 app 的杂物间、而 ``/api/configs/`` 反被 ingest 的
配置仓库读取占着。现在按「一个顶层前缀只归一个域」收口，见 ``handbook/api.md``。
"""

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter(trailing_slash=True)

router.register(r"device-configs", views.DeviceConfigViewSet, basename="device-config")
router.register(r"device-accounts", views.DeviceAccountViewSet, basename="device-account")
router.register(r"vlans", views.VlanViewSet, basename="vlan")
router.register(r"vrfs", views.VrfViewSet, basename="vrf")
router.register(r"interfaces", views.InterfaceViewSet, basename="interface")
router.register(r"snmp-configs", views.SnmpConfigViewSet, basename="snmp-config")
router.register(r"ntp-configs", views.NtpConfigViewSet, basename="ntp-config")
router.register(r"syslog-configs", views.SyslogConfigViewSet, basename="syslog-config")
router.register(r"ltm-virtual-servers", views.LtmVirtualServerViewSet, basename="ltm-vs")
router.register(r"ltm-pools", views.LtmPoolViewSet, basename="ltm-pool")
router.register(r"ltm-pool-members", views.LtmPoolMemberViewSet, basename="ltm-pool-member")
router.register(r"ltm-profiles", views.LtmProfileViewSet, basename="ltm-profile")
router.register(r"ltm-irules", views.LtmIRuleViewSet, basename="ltm-irule")
router.register(r"ltm-snats", views.LtmSNATViewSet, basename="ltm-snat")
router.register(r"ltm-persists", views.LtmPersistViewSet, basename="ltm-persist")
router.register(r"gtm-datacenters", views.GtmDatacenterViewSet, basename="gtm-dc")
router.register(r"gtm-wideips", views.GtmWideipViewSet, basename="gtm-wideip")
router.register(r"gtm-pools", views.GtmPoolViewSet, basename="gtm-pool")
router.register(r"gtm-servers", views.GtmServerViewSet, basename="gtm-server")
router.register(r"gtm-vservers", views.GtmVServerViewSet, basename="gtm-vserver")
router.register(r"address-books", views.AddressBookViewSet, basename="address-book")
router.register(r"services", views.ServiceViewSet, basename="service")
router.register(r"policies", views.PolicyViewSet, basename="policy")
router.register(r"nat-rules", views.NatRuleViewSet, basename="nat-rule")
router.register(r"routes", views.RouteViewSet, basename="route")
router.register(r"arp-mac", views.ArpMacViewSet, basename="arp-mac")

urlpatterns = [
    path("configs/", include(router.urls)),
]
