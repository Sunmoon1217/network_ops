"""巡检任务：任务名对账、调度投递、写库幂等与物化、滚存清理边界。"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.conf import settings
from django.utils import timezone

from analysis import tasks as analysis_tasks
from analysis.models import DashboardMetric, DeviceMetricDaily, InspectionRun, InspectionTarget, InterfaceMetricDaily
from ingest import tasks as ingest_tasks

DAY = "2026-11-24"


def test_task_names_match_settings():
    assert getattr(analysis_tasks.dispatch_inspection, "name") == settings.INSPECTION_DISPATCH_TASK
    assert getattr(analysis_tasks.write_inspection, "name") == settings.INSPECTION_WRITE_TASK
    assert getattr(analysis_tasks.prune_inspection, "name") == settings.INSPECTION_PRUNE_TASK
    assert getattr(ingest_tasks.collect_inspection, "name") == settings.INSPECTION_COLLECT_TASK


@pytest.mark.django_db
def test_dispatch_sends_only_enabled_targets():
    InspectionTarget.objects.create(host="SW-1", ifname="GE1/0/1", enabled=True)
    InspectionTarget.objects.create(host="SW-2", ifname="GE1/0/2", enabled=False)

    with patch("celery.current_app.send_task") as send:
        result = analysis_tasks.dispatch_inspection(DAY, DAY)

    assert result["targets"] == 1
    assert send.call_args.args[0] == settings.INSPECTION_COLLECT_TASK
    date_start, date_end, targets = send.call_args.kwargs["args"]
    assert (date_start, date_end) == (DAY, DAY)
    assert [row["host"] for row in targets] == ["SW-1"]


def _payload(devices=None, interfaces=None):
    now = timezone.now().isoformat()
    return {
        "date_start": DAY,
        "date_end": DAY,
        "devices": devices if devices is not None else [{"date": DAY, "host": "SW-1", "cpu_avg": 10.0, "cpu_max": 20.0, "memory_avg": 30.0, "memory_max": 40.0, "payload": {}}],
        "interfaces": interfaces
        if interfaces is not None
        else [
            {
                "date": DAY,
                "host": "SW-1",
                "ifname": "GE1/0/1",
                "in_bps_avg": 100.0,
                "in_bps_max": 200.0,
                "out_bps_avg": 50.0,
                "out_bps_max": 80.0,
                "in_usage_avg": 10.0,
                "in_usage_max": 20.0,
                "out_usage_avg": 5.0,
                "out_usage_max": 8.0,
                "payload": {},
            }
        ],
        "run": {"status": "success", "device_count": 1, "interface_count": 1, "started_at": now, "finished_at": now, "error": ""},
    }


@pytest.mark.django_db
def test_write_is_idempotent_and_materializes_dashboard():
    analysis_tasks.write_inspection(_payload())
    analysis_tasks.write_inspection(_payload())

    assert DeviceMetricDaily.objects.count() == 1
    assert InterfaceMetricDaily.objects.count() == 1
    assert InspectionRun.objects.count() == 1

    metric = DashboardMetric.objects.get(panel="inspection", group="device", name="list")
    assert metric.list_value == [{"name": "SW-1", "cpu_avg": 10.0, "cpu_max": 20.0, "memory_avg": 30.0, "memory_max": 40.0}]


@pytest.mark.django_db
def test_write_without_devices_keeps_previous_materialization():
    """采集失败 / 无数据时不清空上次成功的大屏数据。"""
    analysis_tasks.write_inspection(_payload())
    analysis_tasks.write_inspection(_payload(devices=[], interfaces=[]))

    metric = DashboardMetric.objects.get(panel="inspection", group="device", name="list")
    assert len(metric.list_value) == 1


@pytest.mark.django_db
def test_prune_removes_rows_older_than_retention(settings):
    settings.INSPECTION_RETENTION_DAYS = 365
    today = timezone.localdate()
    old = today - timedelta(days=400)
    recent = today - timedelta(days=10)

    DeviceMetricDaily.objects.create(date=old, host="OLD")
    DeviceMetricDaily.objects.create(date=recent, host="NEW")
    InterfaceMetricDaily.objects.create(date=old, host="OLD", ifname="GE1/0/1")
    InspectionRun.objects.create(date=old, status="success", started_at=timezone.now())

    result = analysis_tasks.prune_inspection()

    assert result["devices"] == 1
    assert result["interfaces"] == 1
    assert result["runs"] == 1
    assert list(DeviceMetricDaily.objects.values_list("host", flat=True)) == ["NEW"]
    assert not InterfaceMetricDaily.objects.exists()
    assert not InspectionRun.objects.exists()


@pytest.mark.django_db
def test_prune_skipped_when_retention_is_zero(settings):
    settings.INSPECTION_RETENTION_DAYS = 0
    DeviceMetricDaily.objects.create(date=timezone.localdate() - timedelta(days=1000), host="KEEP")

    assert analysis_tasks.prune_inspection() == {"skipped": True}
    assert DeviceMetricDaily.objects.count() == 1
