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


@pytest.mark.django_db
def test_link_linechart_reads_cache_and_returns_meta(monkeypatch):
    """链路 linechart 不再读 MetricSample：从 Redis 缓存拼回旧 EAV 行，并带脱敏 meta。"""
    payload = {
        "window_hours": 3,
        "refreshed_at": "2026-11-11T10:00:00+00:00",
        "panels": [{"id": "internet", "label": "互联网链路使用率", "scopes": ["ipv4"]}],
        "scopes": {"ipv4": "IPv4 互联网链路"},
        "targets": [{"scope": "ipv4", "subject": "zjbgp", "label": "中金BGP", "enabled": True}],
        "points": [{"time": "18:00", "data": {"ipv4": {"zjbgp": 12.3}}}],
    }
    monkeypatch.setattr("analysis.api.dashboard.read_link_cache", lambda: payload)

    body = APIClient().get("/api/dashboard/?panel=link&group=linechart").json()

    assert body["meta"] == {
        "panels": payload["panels"],
        "scopes": payload["scopes"],
        "targets": payload["targets"],
        "window_hours": 3,
        "refreshed_at": payload["refreshed_at"],
    }
    row = [item for item in body["result"] if item["group"] == "linechart"][0]
    assert row["name"] == "bandwidth-18:00"
    assert row["list_value"][0]["data"]["ipv4"]["zjbgp"] == 12.3


@pytest.mark.django_db
def test_link_linechart_cache_miss_returns_empty(monkeypatch):
    """缓存未生成时不报错、不带 meta，前端保留上一次成功结果。"""
    monkeypatch.setattr("analysis.api.dashboard.read_link_cache", lambda: None)

    body = APIClient().get("/api/dashboard/?group=linechart").json()

    assert body["result"] == []
    assert "meta" not in body
