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
router.register(r"device-connections", views.DeviceConnectionViewSet, basename="device-connection")
router.register(r"device-groups", views.DeviceGroupViewSet, basename="device-group")
router.register(r"device-group-members", views.DeviceGroupMemberViewSet, basename="device-group-member")

# Network

# Baseline

# SLB (LTM)

# GSLB (GTM)

# Firewall Policy

# Routing
router.register(r"topologies", views.TopologyViewSet, basename="topology")
router.register(r"subnet-usage-logs", views.SubnetUsageLogViewSet, basename="subnet-usage-log")

# IPAM
router.register(r"tags", views.TagViewSet, basename="tag")
router.register(r"subnets", views.SubnetViewSet, basename="subnet")
router.register(r"ip-addresses", views.IPAddressViewSet, basename="ip-address")

# 统一配置项体系（T1）
router.register(r"configuration-items", views.ConfigurationItemViewSet, basename="configuration-item")
router.register(r"physical-servers", views.PhysicalServerViewSet, basename="physical-server")
router.register(r"virtual-machines", views.VirtualMachineViewSet, basename="virtual-machine")
router.register(r"database-instances", views.DatabaseInstanceViewSet, basename="database-instance")
router.register(r"application-services", views.ApplicationServiceViewSet, basename="application-service")

# 统一关系表（T3）
router.register(r"ci-relationships", views.CIRelationshipViewSet, basename="ci-relationship")

# 软资产（T4）：只读，数据由 sync_soft_assets 归并产出
router.register(r"domain-assets", views.DomainAssetViewSet, basename="domain-asset")
router.register(r"load-balancer-services", views.LoadBalancerServiceViewSet, basename="load-balancer-service")

urlpatterns = [
    path("assets/", include(router.urls)),
    path("assets/overview/", views.overview, name="assets-overview"),
    # Excel 导入 / 模板下载随 device_import.py 迁 ingest.api.urls（URL 与 name 不变）
]
