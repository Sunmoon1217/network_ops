"""大屏供数接口：匿名可读（大屏无人值守，不依赖登录态）。"""

import pytest
from rest_framework.test import APIClient

from assets.models import Cabinet, DataCenter, Device, Room


@pytest.mark.django_db
def test_dashboard_metrics_allow_anonymous():
    """大屏不带 Token 也能拿到指标（响应仍是旧包装）。"""
    response = APIClient().get("/api/dashboard/")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == 200
    assert isinstance(body["result"], list)


@pytest.mark.django_db
def test_dashboard_cabinets_allow_anonymous_and_project_minimal_fields():
    """机柜接口同样免认证，且只投影画 U 位需要的字段。"""
    datacenter = DataCenter.objects.create(name="DC-A")
    room = Room.objects.create(datacenter=datacenter, name="R1")
    cabinet = Cabinet.objects.create(room=room, name="A01", total_u=42)
    Device.objects.create(
        hostname="SW-01", device_type="switch", cabinet=cabinet, u_position=40, height=2
    )

    response = APIClient().get("/api/dashboard/cabinets/")

    assert response.status_code == 200
    result = response.json()["result"]
    assert set(result) == {"cabinets", "devices"}
    assert result["cabinets"][0]["datacenter_name"] == "DC-A"
    assert result["cabinets"][0]["room_name"] == "R1"
    assert result["devices"][0]["cabinet"] == cabinet.pk
    assert result["devices"][0]["device_type_display"] == "交换机"
    assert "remark" not in result["devices"][0]
