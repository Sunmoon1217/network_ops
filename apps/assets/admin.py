# -*- coding: utf-8 -*-
from django.contrib import admin

from .models import (
    AddressBook,
    ArpMac,
    Cabinet,
    DataCenter,
    Device,
    DeviceAccount,
    DeviceConfig,
    DeviceConnection,
    DeviceGroup,
    DeviceGroupMember,
    DeviceModel,
    GtmDatacenter,
    GtmPool,
    GtmServer,
    GtmVServer,
    GtmWideip,
    Interface,
    IPAddress,
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
    Room,
    Route,
    SecurityZone,
    ServerOwner,
    Service,
    SnmpConfig,
    Subnet,
    SubnetUsageLog,
    SyslogConfig,
    Tag,
    Topology,
    Vendor,
    Vlan,
    Vrf,
)

# 全库约 500 台设备：外键过滤器一律 RelatedOnly——只列「库里实际出现过」的对象，
# 下拉不再混入从未被引用的行；表单侧同理统一 autocomplete（可搜索），不用裸 select。
DEVICE_FILTER = ("device", admin.RelatedOnlyFieldListFilter)


@admin.register(SecurityZone)
class SecurityZoneAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "color",
        "description",
        "created_at",
        "updated_at",
    )
    list_filter = ("created_at",)
    search_fields = ("name", "description")
    date_hierarchy = "created_at"


@admin.register(DataCenter)
class DataCenterAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "address",
        "contact",
        "phone",
        "remark",
        "created_at",
        "updated_at",
    )
    list_filter = ("created_at",)
    search_fields = ("name", "address", "contact", "remark")
    date_hierarchy = "created_at"


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "datacenter",
        "contact",
        "remark",
        "created_at",
        "updated_at",
    )
    list_filter = (("datacenter", admin.RelatedOnlyFieldListFilter), "created_at")
    search_fields = ("name", "contact", "remark")
    list_select_related = ("datacenter",)
    date_hierarchy = "created_at"


@admin.register(Cabinet)
class CabinetAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "row",
        "room",
        "total_u",
        "power_capacity",
        "status",
        "remark",
        "created_at",
        "updated_at",
    )
    list_filter = ("status", ("room", admin.RelatedOnlyFieldListFilter), "created_at")
    autocomplete_fields = ("room",)
    search_fields = ("name", "row", "remark")
    list_select_related = ("room",)
    date_hierarchy = "created_at"


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "name_en", "abbr")
    search_fields = ("name", "name_en", "abbr")


@admin.register(DeviceModel)
class DeviceModelAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "vendor")
    list_filter = (("vendor", admin.RelatedOnlyFieldListFilter),)
    search_fields = ("name",)
    list_select_related = ("vendor",)


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "hostname",
        "device_model",
        "device_type",
        "idc",
        "cabinet",
        "security_zone",
        "u_position",
        "height",
        "ip_address",
        "remark",
        "created_at",
        "updated_at",
    )
    # device_type 是最高频的过滤维度（原先只按日期过滤，类型筛不了）
    list_filter = (
        "device_type",
        ("idc", admin.RelatedOnlyFieldListFilter),
        ("security_zone", admin.RelatedOnlyFieldListFilter),
        "created_at",
    )
    autocomplete_fields = ("device_model", "idc", "cabinet", "security_zone")
    search_fields = ("hostname", "ip_address", "remark")
    list_select_related = ("device_model", "idc", "cabinet", "security_zone")
    date_hierarchy = "created_at"


@admin.register(DeviceConnection)
class DeviceConnectionAdmin(admin.ModelAdmin):
    # 明文密码不进列表，详情页查看/编辑
    list_display = (
        "id",
        "device",
        "address",
        "connection_type",
        "driver",
        "port",
        "account_type",
        "username",
        "timeout",
        "enabled",
        "created_at",
        "updated_at",
    )
    list_filter = ("enabled", "connection_type", DEVICE_FILTER, "created_at")
    autocomplete_fields = ("device",)
    search_fields = ("device__hostname", "address", "username")
    list_select_related = ("device",)
    date_hierarchy = "created_at"


class DeviceGroupMemberInline(admin.TabularInline):
    model = DeviceGroupMember
    extra = 1
    autocomplete_fields = ("device",)
    readonly_fields = ("created_at",)


@admin.register(DeviceGroup)
class DeviceGroupAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "group_type", "description", "created_at")
    list_filter = ("group_type", "created_at")
    search_fields = ("name", "description")
    date_hierarchy = "created_at"
    inlines = (DeviceGroupMemberInline,)


@admin.register(DeviceGroupMember)
class DeviceGroupMemberAdmin(admin.ModelAdmin):
    list_display = ("id", "group", "device", "device_role", "created_at")
    list_filter = (
        ("group", admin.RelatedOnlyFieldListFilter),
        "device_role",
        "created_at",
    )
    autocomplete_fields = ("group", "device")
    search_fields = ("group__name", "device__hostname")
    list_select_related = ("group", "device")


@admin.register(DeviceConfig)
class DeviceConfigAdmin(admin.ModelAdmin):
    # config_json 是整份解析结果的大 JSON，不进列表（原先一行把列表页撑爆）；详情页查看
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
    # action（放行/拒绝）原先筛不了，是策略审计最高频的过滤维度
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


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "color", "created_at")
    list_filter = ("created_at",)
    search_fields = ("name",)
    date_hierarchy = "created_at"


@admin.register(Subnet)
class SubnetAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "network",
        "parent",
        "gateway",
        "vlan",
        "datacenter",
        "security_zone",
        "vrf",
        "description",
        "created_at",
        "updated_at",
    )
    list_filter = (
        ("parent", admin.RelatedOnlyFieldListFilter),
        ("datacenter", admin.RelatedOnlyFieldListFilter),
        ("security_zone", admin.RelatedOnlyFieldListFilter),
        "created_at",
    )
    autocomplete_fields = ("parent", "datacenter", "security_zone", "tags")
    search_fields = ("network", "gateway", "vlan", "description")
    list_select_related = ("parent", "datacenter", "security_zone")
    date_hierarchy = "created_at"


@admin.register(IPAddress)
class IPAddressAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "ip_address",
        "subnet",
        "security_zone",
        "status",
        "device",
        "interface",
        "description",
        "created_at",
        "updated_at",
    )
    # status（已使用/预留/可用）原先筛不了
    list_filter = (
        "status",
        ("subnet", admin.RelatedOnlyFieldListFilter),
        ("security_zone", admin.RelatedOnlyFieldListFilter),
        DEVICE_FILTER,
        "created_at",
    )
    autocomplete_fields = ("subnet", "security_zone", "device")
    search_fields = ("ip_address", "interface", "description", "device__hostname")
    list_select_related = ("subnet", "security_zone", "device")
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
    # protocol 原先筛不了；device 继承自 ConfigBase，按设备圈路由是最常用入口
    list_filter = (DEVICE_FILTER, ("vrf", admin.RelatedOnlyFieldListFilter), "protocol", "enabled", "created_at")
    autocomplete_fields = ("device", "vrf")
    search_fields = ("destination", "nexthop", "interface", "description", "device__hostname")
    list_select_related = ("device", "vrf")
    date_hierarchy = "created_at"


@admin.register(Topology)
class TopologyAdmin(admin.ModelAdmin):
    # graph_data 是整张图的大 JSON，不进列表；详情页查看
    list_display = (
        "id",
        "name",
        "description",
        "is_default",
        "created_at",
        "updated_at",
    )
    list_filter = ("is_default", "created_at")
    search_fields = ("name", "description")
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
    # arp_type / status 这类有限取值原先只能翻页碰
    list_filter = (DEVICE_FILTER, "arp_type", "status", "learned_at", "created_at")
    autocomplete_fields = ("device",)
    search_fields = ("ip_address", "mac_address", "interface", "vendor", "device__hostname")
    list_select_related = ("device",)
    date_hierarchy = "created_at"


@admin.register(SubnetUsageLog)
class SubnetUsageLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "subnet",
        "total_ips",
        "used_ips",
        "utilization",
        "recorded_at",
    )
    list_filter = (("subnet", admin.RelatedOnlyFieldListFilter), "recorded_at")
    autocomplete_fields = ("subnet",)
    search_fields = ("subnet__network",)
    list_select_related = ("subnet",)


@admin.register(ServerOwner)
class ServerOwnerAdmin(admin.ModelAdmin):
    list_display = ("id", "ip", "hostname", "owner", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("ip", "hostname", "owner")
    date_hierarchy = "created_at"
