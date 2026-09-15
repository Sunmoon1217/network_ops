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
    DeviceModel,
    GtmDatacenter,
    GtmPool,
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
    list_filter = ("created_at", "updated_at")
    search_fields = ("name",)
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
    list_filter = ("created_at", "updated_at")
    search_fields = ("name",)
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
    list_filter = ("datacenter", "created_at", "updated_at")
    search_fields = ("name",)
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
    list_filter = ("created_at", "updated_at")
    raw_id_fields = ("room",)
    search_fields = ("name",)
    date_hierarchy = "created_at"


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "name_en", "abbr")
    search_fields = ("name",)


@admin.register(DeviceModel)
class DeviceModelAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "vendor")
    search_fields = ("name",)


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
    list_filter = ("created_at", "updated_at")
    raw_id_fields = ("device_model", "idc", "cabinet", "security_zone")
    date_hierarchy = "created_at"


@admin.register(DeviceConnection)
class DeviceConnectionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "address",
        "connection_type",
        "driver",
        "port",
        "account_type",
        "username",
        "password",
        "enable_password",
        "timeout",
        "enabled",
        "created_at",
        "updated_at",
    )
    list_filter = ("enabled", "created_at", "updated_at")
    raw_id_fields = ("device",)
    date_hierarchy = "created_at"


@admin.register(DeviceConfig)
class DeviceConfigAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "git_commit_hash",
        "config_json",
        "parse_duration",
        "collected_at",
        "updated_at",
    )
    list_filter = ("collected_at", "updated_at")
    raw_id_fields = ("device",)
    date_hierarchy = "updated_at"


@admin.register(Vlan)
class VlanAdmin(admin.ModelAdmin):
    list_display = ("id", "device", "vid", "name", "description")
    list_filter = ("device",)
    search_fields = ("name",)


@admin.register(Vrf)
class VrfAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "is_active",
        "created_at",
        "updated_at",
        "name",
        "rd",
        "description",
    )
    list_filter = ("is_active", "created_at", "updated_at")
    search_fields = ("name",)
    date_hierarchy = "created_at"


@admin.register(Interface)
class InterfaceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "is_active",
        "created_at",
        "updated_at",
        "interface",
        "description",
        "enabled",
        "mode",
        "vlans",
        "vrf",
        "type",
        "combo_type",
        "ip_address",
        "subnet_mask",
    )
    list_filter = ("is_active", "created_at", "updated_at", "enabled")
    raw_id_fields = ("device", "vrf")
    date_hierarchy = "created_at"


@admin.register(DeviceAccount)
class DeviceAccountAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "is_active",
        "created_at",
        "updated_at",
        "username",
        "auth_type",
        "privilege",
        "enabled",
        "description",
    )
    list_filter = (
        "device",
        "is_active",
        "created_at",
        "updated_at",
        "enabled",
    )
    date_hierarchy = "created_at"


@admin.register(SnmpConfig)
class SnmpConfigAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "version",
        "community_read",
        "community_write",
        "port",
        "trap_enabled",
        "trap_server",
        "trap_port",
        "enabled",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "device",
        "trap_enabled",
        "enabled",
        "created_at",
        "updated_at",
    )
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
    list_filter = ("device", "enabled", "created_at", "updated_at")
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
    list_filter = ("device", "enabled", "created_at", "updated_at")
    date_hierarchy = "created_at"


@admin.register(LtmVirtualServer)
class LtmVirtualServerAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "is_active",
        "created_at",
        "updated_at",
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
        "profiles",
        "rules",
    )
    list_filter = ("device", "is_active", "created_at", "updated_at")
    search_fields = ("name",)
    date_hierarchy = "created_at"


@admin.register(LtmPool)
class LtmPoolAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "is_active",
        "created_at",
        "updated_at",
        "name",
        "mode",
        "monitors",
    )
    list_filter = ("device", "is_active", "created_at", "updated_at")
    search_fields = ("name",)
    date_hierarchy = "created_at"


@admin.register(LtmPoolMember)
class LtmPoolMemberAdmin(admin.ModelAdmin):
    list_display = ("id", "pool_name", "name", "address")
    search_fields = ("name",)


@admin.register(LtmProfile)
class LtmProfileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "is_active",
        "created_at",
        "updated_at",
        "name",
        "type",
        "raw",
    )
    list_filter = ("device", "is_active", "created_at", "updated_at")
    search_fields = ("name",)
    date_hierarchy = "created_at"


@admin.register(LtmIRule)
class LtmIRuleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "is_active",
        "created_at",
        "updated_at",
        "name",
        "raw",
    )
    list_filter = ("device", "is_active", "created_at", "updated_at")
    search_fields = ("name",)
    date_hierarchy = "created_at"


@admin.register(LtmSNAT)
class LtmSNATAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "is_active",
        "created_at",
        "updated_at",
        "name",
        "address",
    )
    list_filter = ("device", "is_active", "created_at", "updated_at")
    search_fields = ("name",)
    date_hierarchy = "created_at"


@admin.register(LtmPersist)
class LtmPersistAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "is_active",
        "created_at",
        "updated_at",
        "name",
        "type",
        "raw",
    )
    list_filter = ("device", "is_active", "created_at", "updated_at")
    search_fields = ("name",)
    date_hierarchy = "created_at"


@admin.register(GtmDatacenter)
class GtmDatacenterAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "is_active",
        "created_at",
        "updated_at",
        "name",
    )
    list_filter = ("device", "is_active", "created_at", "updated_at")
    search_fields = ("name",)
    date_hierarchy = "created_at"


@admin.register(GtmWideip)
class GtmWideipAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "is_active",
        "created_at",
        "updated_at",
        "name",
        "rtype",
        "lb_mode",
        "pools",
    )
    list_filter = ("device", "is_active", "created_at", "updated_at")
    search_fields = ("name",)
    date_hierarchy = "created_at"


@admin.register(GtmPool)
class GtmPoolAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "is_active",
        "created_at",
        "updated_at",
        "name",
        "lb_mode",
        "alternate_mode",
        "fallback_mode",
        "fallback_ip",
        "ttl",
        "members",
        "monitor",
    )
    list_filter = ("device", "is_active", "created_at", "updated_at")
    search_fields = ("name",)
    date_hierarchy = "created_at"


@admin.register(AddressBook)
class AddressBookAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "is_active",
        "created_at",
        "updated_at",
        "name",
        "address_type",
        "ip_address",
        "ip_netmask",
        "ip_start",
        "ip_end",
        "parent",
        "description",
    )
    list_filter = (
        "device",
        "is_active",
        "created_at",
        "updated_at",
        "parent",
    )
    search_fields = ("name",)
    date_hierarchy = "created_at"


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "is_active",
        "created_at",
        "updated_at",
        "name",
        "protocol",
        "port",
        "port2",
        "description",
    )
    list_filter = ("device", "is_active", "created_at", "updated_at")
    search_fields = ("name",)
    date_hierarchy = "created_at"


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "is_active",
        "created_at",
        "updated_at",
        "policy_id",
        "order",
        "name",
        "action",
        "enabled",
        "log",
        "description",
    )
    list_filter = (
        "device",
        "is_active",
        "created_at",
        "updated_at",
        "enabled",
        "log",
    )
    raw_id_fields = ("source_addresses", "destination_addresses", "services")
    search_fields = ("name",)
    date_hierarchy = "created_at"


@admin.register(NatRule)
class NatRuleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "is_active",
        "created_at",
        "updated_at",
        "order",
        "name",
        "nat_type",
        "enabled",
        "translated_source",
        "translated_destination",
        "translated_service",
        "description",
    )
    list_filter = (
        "device",
        "is_active",
        "created_at",
        "updated_at",
        "enabled",
        "translated_source",
        "translated_destination",
        "translated_service",
    )
    raw_id_fields = ("source_addresses", "destination_addresses", "services")
    search_fields = ("name",)
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
        "parent",
        "datacenter",
        "security_zone",
        "created_at",
        "updated_at",
    )
    raw_id_fields = ("tags",)
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
    list_filter = (
        "subnet",
        "security_zone",
        "device",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "created_at"


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "vrf",
        "destination",
        "nexthop",
        "interface",
        "protocol",
        "metric",
        "enabled",
        "description",
    )
    list_filter = ("vrf", "enabled")


@admin.register(Topology)
class TopologyAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "description",
        "graph_data",
        "is_default",
        "created_at",
        "updated_at",
    )
    list_filter = ("is_default", "created_at", "updated_at")
    search_fields = ("name",)
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
    list_filter = ("device", "learned_at", "created_at", "updated_at")
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
    list_filter = ("subnet", "recorded_at")
