"""配置域路由：与 assets 共用 /api/assets/ 前缀，basename 照抄（前端零改动）。"""

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
    path("assets/", include(router.urls)),
]
