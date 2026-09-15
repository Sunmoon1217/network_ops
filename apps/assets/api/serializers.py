from rest_framework import serializers

from assets.models import (
    Cabinet,
    DataCenter,
    Device,
    DeviceAccount,
    DeviceConfig,
    DeviceConnection,
    DeviceModel,
    Interface,
    NtpConfig,
    Room,
    SecurityZone,
    SnmpConfig,
    SyslogConfig,
    Vendor,
    Vlan,
    Vrf,
)


class SecurityZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = SecurityZone
        fields = ("id", "name", "color", "description", "created_at")
        read_only_fields = ("id", "created_at")


class DataCenterSerializer(serializers.ModelSerializer):
    room_count = serializers.IntegerField(source="rooms.count", read_only=True)
    cabinet_count = serializers.SerializerMethodField()

    class Meta:
        model = DataCenter
        fields = ("id", "name", "address", "contact", "phone", "remark", "room_count", "cabinet_count", "created_at")
        read_only_fields = ("id", "created_at")

    def get_cabinet_count(self, obj) -> int:
        return Cabinet.objects.filter(room__datacenter=obj).count()


class RoomSerializer(serializers.ModelSerializer):
    datacenter_name = serializers.CharField(source="datacenter.name", read_only=True)
    cabinet_count = serializers.IntegerField(source="cabinets.count", read_only=True)

    class Meta:
        model = Room
        fields = ("id", "name", "datacenter", "datacenter_name", "contact", "remark", "cabinet_count", "created_at")
        read_only_fields = ("id", "created_at")


class CabinetSerializer(serializers.ModelSerializer):
    room_name = serializers.CharField(source="room.name", read_only=True)
    datacenter_name = serializers.CharField(source="room.datacenter.name", read_only=True)

    class Meta:
        model = Cabinet
        fields = (
            "id",
            "name",
            "row",
            "room",
            "room_name",
            "datacenter_name",
            "total_u",
            "power_capacity",
            "status",
            "remark",
            "created_at",
        )
        read_only_fields = ("id", "created_at")


class VendorSerializer(serializers.ModelSerializer):
    model_count = serializers.IntegerField(source="device_models.count", read_only=True)

    class Meta:
        model = Vendor
        fields = ("id", "name", "name_en", "abbr", "model_count")
        read_only_fields = ("id",)


class DeviceModelSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)

    class Meta:
        model = DeviceModel
        fields = ("id", "name", "vendor", "vendor_name")
        read_only_fields = ("id",)


class DeviceSerializer(serializers.ModelSerializer):
    idc_name = serializers.CharField(source="idc.name", read_only=True, default="")
    cabinet_name = serializers.CharField(source="cabinet", read_only=True, default="")
    room_name = serializers.CharField(source="cabinet.room.name", read_only=True, default="")
    security_zone_name = serializers.CharField(source="security_zone", read_only=True, default="")
    device_model_name = serializers.CharField(source="device_model", read_only=True, default="")
    device_type_display = serializers.SerializerMethodField()

    def get_device_type_display(self, obj):
        return obj.get_device_type_display() or ""

    class Meta:
        model = Device
        fields = (
            "id",
            "hostname",
            "device_type",
            "device_type_display",
            "device_model",
            "device_model_name",
            "idc",
            "idc_name",
            "cabinet",
            "cabinet_name",
            "room_name",
            "security_zone",
            "security_zone_name",
            "u_position",
            "height",
            "ip_address",
            "remark",
            "created_at",
        )
        read_only_fields = ("id", "created_at")


class DeviceConfigSerializer(serializers.ModelSerializer):
    device_name = serializers.CharField(source="device.hostname", read_only=True)

    class Meta:
        model = DeviceConfig
        fields = ("id", "device", "device_name", "git_commit_hash", "config_json", "parse_duration", "collected_at")
        read_only_fields = ("id", "collected_at")


class DeviceConnectionSerializer(serializers.ModelSerializer):
    device_name = serializers.CharField(source="device.hostname", read_only=True, default="")

    class Meta:
        model = DeviceConnection
        fields = (
            "id",
            "device",
            "device_name",
            "address",
            "connection_type",
            "driver",
            "port",
            "account_type",
            "username",
            "enabled",
            "created_at",
        )
        read_only_fields = ("id", "created_at")
        extra_kwargs = {"password": {"write_only": True}}


class VlanSerializer(serializers.ModelSerializer):
    device_hostname = serializers.CharField(source="device.hostname", read_only=True, default="")

    class Meta:
        model = Vlan
        fields = ("id", "device", "device_hostname", "vid", "name", "description")
        read_only_fields = ("id",)


class VrfSerializer(serializers.ModelSerializer):
    device_hostname = serializers.CharField(source="device.hostname", read_only=True, default="")

    class Meta:
        model = Vrf
        fields = ("id", "device", "device_hostname", "name", "rd", "description", "is_active", "created_at")
        read_only_fields = ("id", "created_at")


class InterfaceSerializer(serializers.ModelSerializer):
    device_hostname = serializers.CharField(source="device.hostname", read_only=True, default="")
    vrf_name = serializers.CharField(source="vrf.name", read_only=True, default="")

    class Meta:
        model = Interface
        fields = (
            "id",
            "device",
            "device_hostname",
            "interface",
            "description",
            "enabled",
            "mode",
            "vlans",
            "vrf",
            "vrf_name",
            "type",
            "combo_type",
            "ip_address",
            "subnet_mask",
            "is_active",
            "created_at",
        )
        read_only_fields = ("id", "created_at")


class DeviceAccountSerializer(serializers.ModelSerializer):
    device_hostname = serializers.CharField(source="device.hostname", read_only=True, default="")

    class Meta:
        model = DeviceAccount
        fields = (
            "id",
            "device",
            "device_hostname",
            "username",
            "auth_type",
            "privilege",
            "enabled",
            "description",
            "is_active",
            "created_at",
        )
        read_only_fields = ("id", "created_at")


class SnmpConfigSerializer(serializers.ModelSerializer):
    device_hostname = serializers.CharField(source="device.hostname", read_only=True, default="")

    class Meta:
        model = SnmpConfig
        fields = (
            "id",
            "device",
            "device_hostname",
            "version",
            "community_read",
            "community_write",
            "port",
            "trap_enabled",
            "trap_server",
            "trap_port",
            "enabled",
            "created_at",
        )
        read_only_fields = ("id", "created_at")


class NtpConfigSerializer(serializers.ModelSerializer):
    device_hostname = serializers.CharField(source="device.hostname", read_only=True, default="")

    class Meta:
        model = NtpConfig
        fields = (
            "id",
            "device",
            "device_hostname",
            "server1",
            "server2",
            "server3",
            "timezone",
            "sync_interval",
            "enabled",
            "created_at",
        )
        read_only_fields = ("id", "created_at")


class SyslogConfigSerializer(serializers.ModelSerializer):
    device_hostname = serializers.CharField(source="device.hostname", read_only=True, default="")

    class Meta:
        model = SyslogConfig
        fields = (
            "id",
            "device",
            "device_hostname",
            "server1",
            "server2",
            "port",
            "facility",
            "level",
            "enabled",
            "created_at",
        )
        read_only_fields = ("id", "created_at")


# ---------------------------------------------------------------------------
# SLB (LTM) Serializers
# ---------------------------------------------------------------------------


class LtmVirtualServerSerializer(serializers.ModelSerializer):
    device_hostname = serializers.CharField(source="device.hostname", read_only=True, default="")

    class Meta:
        from assets.models import LtmVirtualServer

        model = LtmVirtualServer
        fields = (
            "id",
            "device",
            "device_hostname",
            "name",
            "vs_address",
            "vs_port",
            "mask",
            "protocol",
            "pool",
            "snat_type",
            "persist",
            "profiles",
            "rules",
            "is_active",
            "created_at",
        )
        read_only_fields = ("id", "created_at")


class LtmPoolSerializer(serializers.ModelSerializer):
    device_hostname = serializers.CharField(source="device.hostname", read_only=True, default="")

    class Meta:
        from assets.models import LtmPool

        model = LtmPool
        fields = ("id", "device", "device_hostname", "name", "mode", "monitors", "is_active", "created_at")
        read_only_fields = ("id", "created_at")


class LtmPoolMemberSerializer(serializers.ModelSerializer):
    class Meta:
        from assets.models import LtmPoolMember

        model = LtmPoolMember
        fields = ("id", "pool_name", "name", "address")
        read_only_fields = ("id",)


class LtmProfileSerializer(serializers.ModelSerializer):
    device_hostname = serializers.CharField(source="device.hostname", read_only=True, default="")

    class Meta:
        from assets.models import LtmProfile

        model = LtmProfile
        fields = ("id", "device", "device_hostname", "name", "type", "raw", "is_active", "created_at")
        read_only_fields = ("id", "created_at")


class LtmIRuleSerializer(serializers.ModelSerializer):
    device_hostname = serializers.CharField(source="device.hostname", read_only=True, default="")

    class Meta:
        from assets.models import LtmIRule

        model = LtmIRule
        fields = ("id", "device", "device_hostname", "name", "raw", "is_active", "created_at")
        read_only_fields = ("id", "created_at")


class LtmSNATSerializer(serializers.ModelSerializer):
    device_hostname = serializers.CharField(source="device.hostname", read_only=True, default="")

    class Meta:
        from assets.models import LtmSNAT

        model = LtmSNAT
        fields = ("id", "device", "device_hostname", "name", "address", "is_active", "created_at")
        read_only_fields = ("id", "created_at")


class LtmPersistSerializer(serializers.ModelSerializer):
    device_hostname = serializers.CharField(source="device.hostname", read_only=True, default="")

    class Meta:
        from assets.models import LtmPersist

        model = LtmPersist
        fields = ("id", "device", "device_hostname", "name", "type", "raw", "is_active", "created_at")
        read_only_fields = ("id", "created_at")


# ---------------------------------------------------------------------------
# GSLB (GTM) Serializers
# ---------------------------------------------------------------------------


class GtmDatacenterSerializer(serializers.ModelSerializer):
    device_hostname = serializers.CharField(source="device.hostname", read_only=True, default="")

    class Meta:
        from assets.models import GtmDatacenter

        model = GtmDatacenter
        fields = ("id", "device", "device_hostname", "name", "is_active", "created_at")
        read_only_fields = ("id", "created_at")


class GtmWideipSerializer(serializers.ModelSerializer):
    device_hostname = serializers.CharField(source="device.hostname", read_only=True, default="")

    class Meta:
        from assets.models import GtmWideip

        model = GtmWideip
        fields = ("id", "device", "device_hostname", "name", "rtype", "lb_mode", "pools", "is_active", "created_at")
        read_only_fields = ("id", "created_at")


class GtmPoolSerializer(serializers.ModelSerializer):
    device_hostname = serializers.CharField(source="device.hostname", read_only=True, default="")

    class Meta:
        from assets.models import GtmPool

        model = GtmPool
        fields = (
            "id",
            "device",
            "device_hostname",
            "name",
            "lb_mode",
            "alternate_mode",
            "fallback_mode",
            "fallback_ip",
            "ttl",
            "members",
            "monitor",
            "is_active",
            "created_at",
        )
        read_only_fields = ("id", "created_at")


# ---------------------------------------------------------------------------
# Firewall Policy Serializers
# ---------------------------------------------------------------------------


class AddressBookSerializer(serializers.ModelSerializer):
    device_hostname = serializers.CharField(source="device.hostname", read_only=True, default="")
    parent_name = serializers.CharField(source="parent.name", read_only=True, default="")

    class Meta:
        from assets.models import AddressBook

        model = AddressBook
        fields = (
            "id",
            "device",
            "device_hostname",
            "name",
            "address_type",
            "ip_address",
            "ip_netmask",
            "ip_start",
            "ip_end",
            "parent",
            "parent_name",
            "description",
            "is_active",
            "created_at",
        )
        read_only_fields = ("id", "created_at")


class ServiceSerializer(serializers.ModelSerializer):
    device_hostname = serializers.CharField(source="device.hostname", read_only=True, default="")

    class Meta:
        from assets.models import Service

        model = Service
        fields = (
            "id",
            "device",
            "device_hostname",
            "name",
            "protocol",
            "port",
            "port2",
            "description",
            "is_active",
            "created_at",
        )
        read_only_fields = ("id", "created_at")


class PolicySerializer(serializers.ModelSerializer):
    device_hostname = serializers.CharField(source="device.hostname", read_only=True, default="")

    class Meta:
        from assets.models import Policy

        model = Policy
        fields = (
            "id",
            "device",
            "device_hostname",
            "policy_id",
            "order",
            "name",
            "action",
            "enabled",
            "source_addresses",
            "destination_addresses",
            "services",
            "log",
            "description",
            "is_active",
            "created_at",
        )
        read_only_fields = ("id", "created_at")


class NatRuleSerializer(serializers.ModelSerializer):
    device_hostname = serializers.CharField(source="device.hostname", read_only=True, default="")

    class Meta:
        from assets.models import NatRule

        model = NatRule
        fields = (
            "id",
            "device",
            "device_hostname",
            "order",
            "name",
            "nat_type",
            "enabled",
            "source_addresses",
            "destination_addresses",
            "services",
            "translated_source",
            "translated_destination",
            "translated_service",
            "description",
            "is_active",
            "created_at",
        )
        read_only_fields = ("id", "created_at")


# ---------------------------------------------------------------------------
# IPAM Serializers
# ---------------------------------------------------------------------------


class TagSerializer(serializers.ModelSerializer):
    subnet_count = serializers.IntegerField(source="subnets.count", read_only=True)

    class Meta:
        from assets.models import Tag

        model = Tag
        fields = ("id", "name", "color", "subnet_count", "created_at")
        read_only_fields = ("id", "created_at")


class SubnetSerializer(serializers.ModelSerializer):
    tag_names = serializers.SerializerMethodField()
    ip_count = serializers.IntegerField(source="ip_addresses.count", read_only=True)
    total_ips = serializers.IntegerField(read_only=True)
    used_ips = serializers.IntegerField(read_only=True)
    utilization = serializers.FloatField(read_only=True)

    class Meta:
        from assets.models import Subnet

        model = Subnet
        fields = (
            "id",
            "network",
            "tags",
            "tag_names",
            "parent",
            "gateway",
            "vlan",
            "datacenter",
            "security_zone",
            "vrf",
            "description",
            "ip_count",
            "total_ips",
            "used_ips",
            "utilization",
            "created_at",
        )
        read_only_fields = ("id", "created_at")

    def get_tag_names(self, obj):
        return list(obj.tags.values_list("name", flat=True))


class IPAddressSerializer(serializers.ModelSerializer):
    device_hostname = serializers.CharField(source="device.hostname", read_only=True, default="")
    subnet_network = serializers.CharField(source="subnet.network", read_only=True, default="")
    security_zone_name = serializers.CharField(source="security_zone.name", read_only=True, default="")

    class Meta:
        from assets.models import IPAddress

        model = IPAddress
        fields = (
            "id",
            "ip_address",
            "subnet",
            "subnet_network",
            "security_zone",
            "security_zone_name",
            "status",
            "device",
            "device_hostname",
            "interface",
            "description",
            "created_at",
        )
        read_only_fields = ("id", "created_at")


class RouteSerializer(serializers.ModelSerializer):
    device_hostname = serializers.CharField(source="vrf.device.hostname", read_only=True, default="")
    vrf_name = serializers.CharField(source="vrf.name", read_only=True, default="")

    class Meta:
        from assets.models import Route

        model = Route
        fields = (
            "id",
            "vrf",
            "vrf_name",
            "device_hostname",
            "destination",
            "nexthop",
            "interface",
            "protocol",
            "metric",
            "enabled",
            "description",
        )
        read_only_fields = ("id",)


class TopologySerializer(serializers.ModelSerializer):
    class Meta:
        from assets.models import Topology

        model = Topology
        fields = ("id", "name", "description", "graph_data", "is_default", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class ArpMacSerializer(serializers.ModelSerializer):
    device_hostname = serializers.CharField(source="device.hostname", read_only=True, default="")

    class Meta:
        from assets.models import ArpMac

        model = ArpMac
        fields = (
            "id",
            "device",
            "device_hostname",
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
        read_only_fields = ("id", "created_at", "updated_at")


class SubnetUsageLogSerializer(serializers.ModelSerializer):
    subnet_network = serializers.CharField(source="subnet.network", read_only=True, default="")

    class Meta:
        from assets.models import SubnetUsageLog

        model = SubnetUsageLog
        fields = ("id", "subnet", "subnet_network", "total_ips", "used_ips", "utilization", "recorded_at")
        read_only_fields = ("id", "recorded_at")
