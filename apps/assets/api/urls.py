from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter(trailing_slash=True)

# DCIM
router.register(r"security-zones", views.SecurityZoneViewSet, basename="security-zone")
router.register(r"datacenters", views.DataCenterViewSet, basename="datacenter")
router.register(r"rooms", views.RoomViewSet, basename="room")
router.register(r"cabinets", views.CabinetViewSet, basename="cabinet")

# Device
router.register(r"vendors", views.VendorViewSet, basename="vendor")
router.register(r"device-models", views.DeviceModelViewSet, basename="device-model")
router.register(r"devices", views.DeviceViewSet, basename="device")
router.register(r"device-configs", views.DeviceConfigViewSet, basename="device-config")
router.register(r"device-connections", views.DeviceConnectionViewSet, basename="device-connection")
router.register(r"device-accounts", views.DeviceAccountViewSet, basename="device-account")

# Network
router.register(r"vlans", views.VlanViewSet, basename="vlan")
router.register(r"vrfs", views.VrfViewSet, basename="vrf")
router.register(r"interfaces", views.InterfaceViewSet, basename="interface")

# Baseline
router.register(r"snmp-configs", views.SnmpConfigViewSet, basename="snmp-config")
router.register(r"ntp-configs", views.NtpConfigViewSet, basename="ntp-config")
router.register(r"syslog-configs", views.SyslogConfigViewSet, basename="syslog-config")

# SLB (LTM)
router.register(r"ltm-virtual-servers", views.LtmVirtualServerViewSet, basename="ltm-vs")
router.register(r"ltm-pools", views.LtmPoolViewSet, basename="ltm-pool")
router.register(r"ltm-pool-members", views.LtmPoolMemberViewSet, basename="ltm-pool-member")
router.register(r"ltm-profiles", views.LtmProfileViewSet, basename="ltm-profile")
router.register(r"ltm-irules", views.LtmIRuleViewSet, basename="ltm-irule")
router.register(r"ltm-snats", views.LtmSNATViewSet, basename="ltm-snat")
router.register(r"ltm-persists", views.LtmPersistViewSet, basename="ltm-persist")

# GSLB (GTM)
router.register(r"gtm-datacenters", views.GtmDatacenterViewSet, basename="gtm-dc")
router.register(r"gtm-wideips", views.GtmWideipViewSet, basename="gtm-wideip")
router.register(r"gtm-pools", views.GtmPoolViewSet, basename="gtm-pool")

# Firewall Policy
router.register(r"address-books", views.AddressBookViewSet, basename="address-book")
router.register(r"services", views.ServiceViewSet, basename="service")
router.register(r"policies", views.PolicyViewSet, basename="policy")
router.register(r"nat-rules", views.NatRuleViewSet, basename="nat-rule")

# Routing
router.register(r"routes", views.RouteViewSet, basename="route")
router.register(r"topologies", views.TopologyViewSet, basename="topology")
router.register(r"arp-mac", views.ArpMacViewSet, basename="arp-mac")
router.register(r"subnet-usage-logs", views.SubnetUsageLogViewSet, basename="subnet-usage-log")

# IPAM
router.register(r"tags", views.TagViewSet, basename="tag")
router.register(r"subnets", views.SubnetViewSet, basename="subnet")
router.register(r"ip-addresses", views.IPAddressViewSet, basename="ip-address")

urlpatterns = [
    path("assets/", include(router.urls)),
    path("assets/overview/", views.overview, name="assets-overview"),
    path("assets/import-devices/", views.import_excel, name="import-devices"),
]
