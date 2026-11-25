"""巡检 API：日指标 / 批次只读，采集目标可写，权限走全局 IsOperatorOrReadOnly。"""

import pytest
from django.utils import timezone

from analysis.models import DeviceMetricDaily, InspectionRun, InspectionTarget

TARGETS_URL = "/api/analysis/inspection-targets/"
RUNS_URL = "/api/analysis/inspection-runs/"
DEVICES_URL = "/api/analysis/inspection-devices/"


@pytest.mark.django_db
def test_operator_can_create_update_and_delete_target(operator_client):
    resp = operator_client.post(
        TARGETS_URL,
        {"host": "SW-1", "ifname": "GE1/0/1", "itemids": [" 10 ", ""], "enabled": True},
        format="json",
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["itemids"] == ["10"]
    assert data["enabled"] is True

    patch = operator_client.patch(f"{TARGETS_URL}{data['id']}/", {"enabled": False}, format="json")
    assert patch.status_code == 200
    assert patch.json()["enabled"] is False

    assert operator_client.delete(f"{TARGETS_URL}{data['id']}/").status_code == 204
    assert not InspectionTarget.objects.exists()


@pytest.mark.django_db
def test_target_rejects_duplicate_and_non_string_itemids(operator_client):
    InspectionTarget.objects.create(host="SW-1", ifname="GE1/0/1")

    duplicate = operator_client.post(TARGETS_URL, {"host": "SW-1", "ifname": "GE1/0/1"}, format="json")
    assert duplicate.status_code == 400

    invalid = operator_client.post(TARGETS_URL, {"host": "SW-2", "ifname": "GE1/0/1", "itemids": [1]}, format="json")
    assert invalid.status_code == 400
    assert "itemids" in invalid.json()


@pytest.mark.django_db
def test_normal_user_can_read_targets_but_not_write(api_client):
    InspectionTarget.objects.create(host="SW-1", ifname="GE1/0/1")

    assert api_client.get(TARGETS_URL).status_code == 200
    assert api_client.post(TARGETS_URL, {"host": "SW-2", "ifname": "GE1/0/2"}, format="json").status_code == 403


@pytest.mark.django_db
def test_devices_default_to_latest_day_and_date_filter(api_client):
    DeviceMetricDaily.objects.create(date="2026-11-23", host="SW-OLD", cpu_avg=1.0)
    DeviceMetricDaily.objects.create(date="2026-11-24", host="SW-NEW", cpu_avg=2.0)

    latest = api_client.get(DEVICES_URL).json()
    assert latest["count"] == 1
    assert latest["results"][0]["host"] == "SW-NEW"

    pinned = api_client.get(DEVICES_URL, {"date": "2026-11-23"}).json()
    assert pinned["results"][0]["host"] == "SW-OLD"


@pytest.mark.django_db
def test_runs_are_read_only(operator_client):
    InspectionRun.objects.create(date=timezone.localdate(), status="success", started_at=timezone.now())

    listed = operator_client.get(RUNS_URL).json()
    assert listed["count"] == 1
    assert listed["results"][0]["status"] == "success"
    assert operator_client.post(RUNS_URL, {"status": "success"}, format="json").status_code == 405
