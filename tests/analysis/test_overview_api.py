"""``/api/assets/overview/`` 的响应契约（Home 页一次拿全所有卡片与图表数据）。

这个端点 2026-11-16 从 ``assets/api/views.py`` 迁到 ``analysis/api/overview.py``——因为它是
assets + configs 的跨域聚合，留在 assets 会让叶子节点往上够。**迁的是实现位置，不是契约**：
路径、name、响应字段一个都没变，前端 ``views/Home.vue`` 整包消费。

所以这里用一份冻结的键清单锁住：字段少一个前端就是一块空白卡片，且没有任何类型系统
能提前发现（``data.value = resp.data`` 是 any）。新增字段要同步改这份清单。
"""

import pytest
from rest_framework.test import APIClient

from assets.models import Device
from configs.models import Vlan

OVERVIEW_URL = "/api/assets/overview/"

#: 响应顶层字段全清单（41 个）。分组的注释与视图里的分段保持一致。
EXPECTED_KEYS = {
    # 基础设施
    "dc_count",
    "room_count",
    "cabinet_count",
    "cabinet_active",
    "cabinets_by_dc",
    "cabinets_by_status",
    "security_zone_count",
    # 设备
    "device_count",
    "device_types",
    "vendor_count",
    "device_model_count",
    "devices_by_vendor",
    "devices_by_zone",
    # 接口
    "interface_count",
    "interface_up",
    "interface_modes",
    # 网络（VLAN / VRF / 路由）
    "vlan_count",
    "vrf_count",
    "route_count",
    "route_protocols",
    "routes_by_device",
    # 负载均衡
    "vs_count",
    "pool_count",
    "pool_member_count",
    "vs_by_protocol",
    "pools_by_lb",
    # 全局负载均衡
    "gtm_dc_count",
    "gtm_wideip_count",
    "gtm_pool_count",
    # 防火墙
    "address_book_count",
    "service_count",
    "policy_count",
    "nat_rule_count",
    "policies_by_action",
    "nat_by_type",
    "address_books_by_type",
    "services_by_protocol",
    # IPAM
    "subnet_count",
    "arp_mac_count",
    "subnets_by_dc",
    "subnets_by_zone",
}


def _auth_client(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_overview_response_contract(normal_user):
    """普通用户 200，且顶层字段与冻结清单完全一致（多一个少一个都算破坏契约）。"""
    resp = _auth_client(normal_user).get(OVERVIEW_URL)

    assert resp.status_code == 200
    assert set(resp.json()) == EXPECTED_KEYS, f"缺字段：{sorted(EXPECTED_KEYS - set(resp.json()))}\n多字段：{sorted(set(resp.json()) - EXPECTED_KEYS)}"


@pytest.mark.django_db
def test_overview_counts_both_domains(normal_user):
    """聚合两侧都要覆盖：assets 的 device_count 与 configs 的 vlan_count 同时生效。

    这是「必须住在上层域」的原因本身——一旦实现只能看到一个域，这个用例会先失败。
    """
    Device.objects.create(hostname="overview-dev", device_type="switch")
    Vlan.objects.create(device=Device.objects.get(hostname="overview-dev"), vid=100, name="ov-100")

    payload = _auth_client(normal_user).get(OVERVIEW_URL).json()

    assert payload["device_count"] >= 1
    assert payload["vlan_count"] >= 1
