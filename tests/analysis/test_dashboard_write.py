"""Dashboard 写库侧：任务名对账、A/C payload 解析、幂等 upsert。"""

import json
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.utils import timezone

from analysis import tasks as analysis_tasks
from analysis.models import CollectionRun, DashboardMetric, ItsmCase, MetricSample


def test_write_task_name_matches_settings():
    assert analysis_tasks.write_dashboard.name == settings.DASHBOARD_WRITE_TASK


def test_resolve_payload_a_returns_as_is():
    payload = {"source": "zabbix"}
    assert analysis_tasks._resolve_payload(payload) is payload


def test_resolve_payload_c_reads_redis_key():
    client = MagicMock()
    client.get.return_value = json.dumps({"source": "autotask"})
    with patch.object(analysis_tasks, "_dashboard_redis", return_value=client):
        result = analysis_tasks._resolve_payload({"__redis_key__": "dashboard:batch:x"})
    assert result == {"source": "autotask"}
    client.delete.assert_called_once_with("dashboard:batch:x")


def test_resolve_payload_c_missing_key_fails_loud():
    client = MagicMock()
    client.get.return_value = None
    with patch.object(analysis_tasks, "_dashboard_redis", return_value=client), pytest.raises(ValueError, match="已过期或丢失"):
        analysis_tasks._resolve_payload({"__redis_key__": "dashboard:batch:x"})


@pytest.mark.django_db(transaction=True)
def test_write_dashboard_is_idempotent():
    """同一 payload 投递两次：唯一键 upsert，不产生重复行。"""
    now = timezone.now().isoformat()
    payload = {
        "source": "autotask",
        "batch_at": now,
        "metrics": [{"panel": "statusbar", "group": "devicecount", "name": "count", "value": None, "list_value": [{"count": 3}], "sampled_at": now}],
        "samples": [{"kind": "device_cpu", "scope": "switch", "subject": "SW-1", "metric_key": "cpu.util", "value": 12.5, "payload": {}, "sampled_at": now}],
        "cases": [{"case_no": "GD-1", "title": "变更单", "applicant": "张三", "raw": {"case_no": "GD-1", "title": "变更单", "status": "成功"}}],
        "run": {"status": "success", "item_count": 3, "started_at": now, "finished_at": now, "error": ""},
    }
    analysis_tasks.write_dashboard(payload)
    analysis_tasks.write_dashboard(payload)

    assert DashboardMetric.objects.filter(panel="statusbar", group="devicecount", name="count").count() == 1
    assert DashboardMetric.objects.filter(panel="itsmtask", group="case", name="GD-1").count() == 1
    assert MetricSample.objects.filter(kind="device_cpu", subject="SW-1").count() == 1
    assert ItsmCase.objects.filter(case_no="GD-1", is_active=True).count() == 1
    assert CollectionRun.objects.count() == 2  # 每次批次都留痕，不覆盖


@pytest.mark.django_db(transaction=True)
def test_write_dashboard_records_failed_run_when_upsert_breaks():
    """写库失败不能只在 celery 里红一下：补一条 failed 的 CollectionRun（大屏新鲜度要靠它）。"""
    now = timezone.now().isoformat()
    payload = {
        "source": "zabbix",
        "batch_at": now,
        "metrics": [{"panel": "statusbar", "group": "devicecount", "name": "count", "value": None, "list_value": [{"count": 1}], "sampled_at": now}],
        "samples": [],
        "cases": [],
        "run": {"status": "success", "item_count": 1, "started_at": now, "finished_at": now, "error": ""},
    }

    with patch.object(DashboardMetric.objects, "update_or_create", side_effect=RuntimeError("db down")), pytest.raises(RuntimeError, match="db down"):
        analysis_tasks.write_dashboard(payload)

    run = CollectionRun.objects.get()
    assert run.status == "failed"
    assert run.source == "zabbix"
    assert "db down" in run.error
