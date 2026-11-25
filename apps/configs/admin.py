"""配置域 admin：配置行家族 26 个模型（含 ArpMac）与 DeviceConfig 快照。

列表 / 搜索 / 筛选口径与 assets/admin.py 一致。
"""

from django.contrib import admin

from configs.models import (
    AddressBook,
    ArpMac,
    DeviceAccount,
    DeviceConfig,
    GtmDatacenter,
    GtmPool,
    GtmServer,
    GtmVServer,
    GtmWideip,
    Interface,
    LtmIRule,
    LtmPersist,
    LtmPool,
    LtmPoolMember,
    LtmProfile,
    LtmSNAT,
    LtmVirtualServer,
    NatRule,
    NtpConfig,
    Policy,
    Route,
    Service,
    SnmpConfig,
    SyslogConfig,
    Vlan,
    Vrf,
)

# 全库约 500 台设备：外键过滤器一律 RelatedOnly（与 assets/admin.py 同一口径）
DEVICE_FILTER = ("device", admin.RelatedOnlyFieldListFilter)


@admin.register(DeviceConfig)
class DeviceConfigAdmin(admin.ModelAdmin):
    # config_json 是整份解析结果的大 JSON，不进列表；详情页查看
    list_display = (
        "id",
        "device",
        "git_commit_hash",
        "parse_duration",
        "collected_at",
        "updated_at",
    )
    list_filter = (DEVICE_FILTER, "collected_at")
    autocomplete_fields = ("device",)
    search_fields = ("device__hostname", "git_commit_hash")
    list_select_related = ("device",)
    date_hierarchy = "updated_at"


@admin.register(Vlan)
class VlanAdmin(admin.ModelAdmin):
    list_display = ("id", "device", "vid", "name", "description")
    list_filter = (DEVICE_FILTER, "created_at")
    autocomplete_fields = ("device",)
    search_fields = ("name", "description", "device__hostname")
    list_select_related = ("device",)


@admin.register(Vrf)
class VrfAdmin(admin.ModelAdmin):
    # 时间列挪到行尾：名称 / RD 才是这页要先看到的
    list_display = (
        "id",
        "device",
        "is_active",
        "name",
        "rd",
        "description",
        "created_at",
        "updated_at",
    )
    list_filter = (DEVICE_FILTER, "is_active", "created_at")
    autocomplete_fields = ("device",)
    search_fields = ("name", "rd", "description", "device__hostname")
    list_select_related = ("device",)
    date_hierarchy = "created_at"


@admin.register(Interface)
class InterfaceAdmin(admin.ModelAdmin):
    # vlans 是 JSON 配置，不进列表；详情页查看
    list_display = (
        "id",
        "device",
        "is_active",
        "interface",
        "description",
        "enabled",
        "mode",
        "vrf",
        "type",
        "combo_type",
        "ip_address",
        "subnet_mask",
        "created_at",
        "updated_at",
    )
    list_filter = (DEVICE_FILTER, "is_active", "enabled", "created_at")
    autocomplete_fields = ("device", "vrf")
    search_fields = ("interface", "description", "ip_address", "device__hostname")
    list_select_related = ("device", "vrf")
    date_hierarchy = "created_at"


@admin.register(DeviceAccount)
class DeviceAccountAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "is_active",
        "username",
        "auth_type",
        "privilege",
        "enabled",
        "description",
        "created_at",
        "updated_at",
    )
    list_filter = (DEVICE_FILTER, "is_active", "enabled", "created_at")
    autocomplete_fields = ("device",)
    search_fields = ("username", "description", "device__hostname")
    list_select_related = ("device",)
    date_hierarchy = "created_at"


@admin.register(SnmpConfig)
class SnmpConfigAdmin(admin.ModelAdmin):
    # 社区字符串（准口令）不进列表，详情页查看
    list_display = (
        "id",
        "device",
        "version",
        "port",
        "trap_enabled",
        "trap_server",
        "trap_port",
        "enabled",
        "created_at",
        "updated_at",
    )
    list_filter = (DEVICE_FILTER, "version", "trap_enabled", "enabled", "created_at")
    autocomplete_fields = ("device",)
    search_fields = ("device__hostname", "trap_server")
    list_select_related = ("device",)
    date_hierarchy = "created_at"


@admin.register(NtpConfig)
class NtpConfigAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "server1",
        "server2",
        "server3",
        "timezone",
        "sync_interval",
        "enabled",
        "created_at",
        "updated_at",
    )
    list_filter = (DEVICE_FILTER, "enabled", "created_at")
    autocomplete_fields = ("device",)
    search_fields = ("server1", "server2", "server3", "device__hostname")
    list_select_related = ("device",)
    date_hierarchy = "created_at"


@admin.register(SyslogConfig)
class SyslogConfigAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "server1",
        "server2",
        "port",
        "facility",
        "level",
        "enabled",
        "created_at",
        "updated_at",
    )
    list_filter = (DEVICE_FILTER, "enabled", "created_at")
    autocomplete_fields = ("device",)
    search_fields = ("server1", "server2", "device__hostname")
    list_select_related = ("device",)
    date_hierarchy = "created_at"


@admin.register(LtmVirtualServer)
class LtmVirtualServerAdmin(admin.ModelAdmin):
    # profiles / rules 是 JSON 列表，不进列表；详情页查看
    list_display = (
        "id",
        "device",
        "is_active",
        "name",
        "vs_address",
        "vs_port",
        "mask",
        "protocol",
        "source",
        "snat_type",
        "pool",
        "snat_pool",
        "persist",
        "created_at",
        "updated_at",
    )
    list_filter = (DEVICE_FILTER, "is_active", "created_at")
    autocomplete_fields = ("device",)
    search_fields = ("name", "vs_address", "pool", "device__hostname")
    list_select_related = ("device",)
    date_hierarchy = "created_at"


@admin.register(LtmPool)
class LtmPoolAdmin(admin.ModelAdmin):
    # monitors 是 JSON 列表，不进列表；详情页查看
    list_display = (
        "id",
        "device",
        "is_active",
        "name",
        "mode",
        "created_at",
        "updated_at",
    )
    list_filter = (DEVICE_FILTER, "is_active", "created_at")
    autocomplete_fields = ("device",)
    search_fields = ("name", "device__hostname")
    list_select_related = ("device",)
    date_hierarchy = "created_at"


@admin.register(LtmPoolMember)
class LtmPoolMemberAdmin(admin.ModelAdmin):
    list_display = ("id", "device", "pool_name", "name", "address", "port", "is_active", "created_at")
    list_filter = (DEVICE_FILTER, "is_active", "created_at")
    autocomplete_fields = ("device",)
    search_fields = ("name", "address", "pool_name", "device__hostname")
    list_select_related = ("device",)
    date_hierarchy = "created_at"


@admin.register(LtmProfile)
class LtmProfileAdmin(admin.ModelAdmin):
    # raw 是原始配置大 JSON，不进列表；详情页查看
    list_display = (
        "id",
        "device",
        "is_active",
        "name",
        "type",
        "created_at",
        "updated_at",
    )
    list_filter = (DEVICE_FILTER, "is_active", "created_at")
    autocomplete_fields = ("device",)
    search_fields = ("name", "type", "device__hostname")
    list_select_related = ("device",)
    date_hierarchy = "created_at"


@admin.register(LtmIRule)
class LtmIRuleAdmin(admin.ModelAdmin):
    # raw 同上，不进列表
    list_display = (
        "id",
        "device",
        "is_active",
        "name",
        "created_at",
        "updated_at",
    )
    list_filter = (DEVICE_FILTER, "is_active", "created_at")
    autocomplete_fields = ("device",)
    search_fields = ("name", "device__hostname")
    list_select_related = ("device",)
    date_hierarchy = "created_at"


@admin.register(LtmSNAT)
class LtmSNATAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "is_active",
        "name",
        "address",
        "created_at",
        "updated_at",
    )
    list_filter = (DEVICE_FILTER, "is_active", "created_at")
    autocomplete_fields = ("device",)
    search_fields = ("name", "address", "device__hostname")
    list_select_related = ("device",)
    date_hierarchy = "created_at"


@admin.register(LtmPersist)
class LtmPersistAdmin(admin.ModelAdmin):
    # raw 同上，不进列表
    list_display = (
        "id",
        "device",
        "is_active",
        "name",
        "type",
        "created_at",
        "updated_at",
    )
    list_filter = (DEVICE_FILTER, "is_active", "created_at")
    autocomplete_fields = ("device",)
    search_fields = ("name", "type", "device__hostname")
    list_select_related = ("device",)
    date_hierarchy = "created_at"


@admin.register(GtmDatacenter)
class GtmDatacenterAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "is_active",
        "name",
        "created_at",
        "updated_at",
    )
    list_filter = (DEVICE_FILTER, "is_active", "created_at")
    autocomplete_fields = ("device",)
    search_fields = ("name", "device__hostname")
    list_select_related = ("device",)
    date_hierarchy = "created_at"


@admin.register(GtmWideip)
class GtmWideipAdmin(admin.ModelAdmin):
    # pools 是 JSON 列表，不进列表；详情页查看
    list_display = (
        "id",
        "device",
        "is_active",
        "name",
        "rtype",
        "lb_mode",
        "created_at",
        "updated_at",
    )
    list_filter = (DEVICE_FILTER, "is_active", "created_at")
    autocomplete_fields = ("device",)
    search_fields = ("name", "device__hostname")
    list_select_related = ("device",)
    date_hierarchy = "created_at"


@admin.register(GtmPool)
class GtmPoolAdmin(admin.ModelAdmin):
    # members / monitor 是 JSON 列表，不进列表；详情页查看
    list_display = (
        "id",
        "device",
        "is_active",
        "name",
        "lb_mode",
        "alternate_mode",
        "fallback_mode",
        "fallback_ip",
        "ttl",
        "created_at",
        "updated_at",
    )
    list_filter = (DEVICE_FILTER, "is_active", "created_at")
    autocomplete_fields = ("device",)
    search_fields = ("name", "fallback_ip", "device__hostname")
    list_select_related = ("device",)
    date_hierarchy = "created_at"


@admin.register(GtmServer)
class GtmServerAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "is_active",
        "name",
        "datacenter",
        "server_type",
        "monitor",
        "created_at",
        "updated_at",
    )
    list_filter = (DEVICE_FILTER, "is_active", "created_at")
    autocomplete_fields = ("device",)
    search_fields = ("name", "datacenter", "device__hostname")
    list_select_related = ("device",)
    date_hierarchy = "created_at"


@admin.register(GtmVServer)
class GtmVServerAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "server",
        "is_active",
        "name",
        "ip_address",
        "port",
        "monitor",
        "created_at",
        "updated_at",
    )
    list_filter = (
        DEVICE_FILTER,
        ("server", admin.RelatedOnlyFieldListFilter),
        "is_active",
        "created_at",
    )
    autocomplete_fields = ("device", "server")
    search_fields = ("name", "ip_address", "device__hostname", "server__name")
    list_select_related = ("device", "server")
    date_hierarchy = "created_at"


@admin.register(AddressBook)
class AddressBookAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "is_active",
        "name",
        "address_type",
        "ip_address",
        "ip_netmask",
        "ip_start",
        "ip_end",
        "parent",
        "description",
        "created_at",
        "updated_at",
    )
    list_filter = (
        DEVICE_FILTER,
        "address_type",
        "is_active",
        ("parent", admin.RelatedOnlyFieldListFilter),
        "created_at",
    )
    autocomplete_fields = ("device", "parent")
    search_fields = ("name", "description", "ip_address", "device__hostname")
    list_select_related = ("device", "parent")
    date_hierarchy = "created_at"


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "is_active",
        "name",
        "protocol",
        "port",
        "port2",
        "description",
        "created_at",
        "updated_at",
    )
    list_filter = (DEVICE_FILTER, "protocol", "is_active", "created_at")
    autocomplete_fields = ("device",)
    search_fields = ("name", "description", "device__hostname")
    list_select_related = ("device",)
    date_hierarchy = "created_at"


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "is_active",
        "policy_id",
        "order",
        "name",
        "action",
        "enabled",
        "log",
        "description",
        "created_at",
        "updated_at",
    )
    list_filter = (DEVICE_FILTER, "action", "is_active", "enabled", "log", "created_at")
    autocomplete_fields = ("device", "source_addresses", "destination_addresses", "services")
    search_fields = ("name", "policy_id", "description", "device__hostname")
    list_select_related = ("device",)
    date_hierarchy = "created_at"


@admin.register(NatRule)
class NatRuleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "is_active",
        "order",
        "name",
        "nat_type",
        "enabled",
        "translated_source",
        "translated_destination",
        "translated_service",
        "description",
        "created_at",
        "updated_at",
    )
    # translated_* 指向整个地址簿/服务表，过滤下拉动辄上千项，换成 nat_type 这个
    # 有限取值；要按具体地址找规则走搜索
    list_filter = (DEVICE_FILTER, "nat_type", "is_active", "enabled", "created_at")
    autocomplete_fields = (
        "device",
        "source_addresses",
        "destination_addresses",
        "services",
        "translated_source",
        "translated_destination",
        "translated_service",
    )
    search_fields = ("name", "description", "device__hostname")
    list_select_related = ("device", "translated_source", "translated_destination", "translated_service")
    date_hierarchy = "created_at"


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "vrf",
        "destination",
        "nexthop",
        "interface",
        "protocol",
        "metric",
        "enabled",
        "description",
        "created_at",
        "updated_at",
    )
    # device 继承自 ConfigBase，按设备圈路由是最常用入口
    list_filter = (DEVICE_FILTER, ("vrf", admin.RelatedOnlyFieldListFilter), "protocol", "enabled", "created_at")
    autocomplete_fields = ("device", "vrf")
    search_fields = ("destination", "nexthop", "interface", "description", "device__hostname")
    list_select_related = ("device", "vrf")
    date_hierarchy = "created_at"


@admin.register(ArpMac)
class ArpMacAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "vlan",
        "interface",
        "ip_address",
        "mac_address",
        "vendor",
        "arp_type",
        "learned_at",
        "status",
        "created_at",
        "updated_at",
    )
    list_filter = (DEVICE_FILTER, "arp_type", "status", "learned_at", "created_at")
    autocomplete_fields = ("device",)
    search_fields = ("ip_address", "mac_address", "interface", "vendor", "device__hostname")
    list_select_related = ("device",)
    date_hierarchy = "created_at"
