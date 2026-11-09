"""Dashboard 采集侧边界：任务留在 ingest、只按任务名字符串投递、不写数据库。

对照 ``tests/ingest/test_access_flow_trigger.py`` 的同一条边界：投递侧不 import analysis。
"""

from unittest.mock import AsyncMock, MagicMock, patch

from django.conf import settings

from analysis import tasks as analysis_tasks
from ingest import tasks as ingest_tasks

PAYLOAD = {
    "source": "zabbix",
    "batch_at": "2026-11-09T10:00:00+00:00",
    "metrics": [],
    "samples": [],
    "cases": [],
    "run": {
        "status": "success",
        "item_count": 0,
        "started_at": "2026-11-09T10:00:00+00:00",
        "finished_at": "2026-11-09T10:00:01+00:00",
        "error": "",
    },
}


def test_task_names_match_settings():
    """任务名唯一定义处 = 写库任务装饰器 name；采集任务名固定在 ingest。"""
    assert settings.DASHBOARD_WRITE_TASK == "analysis.write_dashboard"
    assert ingest_tasks.collect_dashboard.name == "ingest.collect_dashboard"
    assert analysis_tasks.write_dashboard.name == settings.DASHBOARD_WRITE_TASK


def test_a_delivers_payload_directly(settings):
    """A：payload 原样随消息投递，采集任务不碰 ORM。"""
    settings.DASHBOARD_PAYLOAD_VIA_REDIS = False
    with (
        patch("ingest.collectors.dashboard.collect", new=AsyncMock(return_value=PAYLOAD)),
        patch("celery.current_app.send_task") as send,
    ):
        ingest_tasks.collect_dashboard("zabbix")

    assert send.call_args.args[0] == settings.DASHBOARD_WRITE_TASK
    assert send.call_args.kwargs["args"][0] is PAYLOAD


def test_c_delivers_only_redis_key(settings):
    """C：payload 暂存 Redis，消息里只带 key。"""
    settings.DASHBOARD_PAYLOAD_VIA_REDIS = True
    client = MagicMock()
    with (
        patch("ingest.collectors.dashboard.collect", new=AsyncMock(return_value=PAYLOAD)),
        patch.object(ingest_tasks, "_dashboard_redis", return_value=client),
        patch("celery.current_app.send_task") as send,
    ):
        ingest_tasks.collect_dashboard("zabbix")

    delivery = send.call_args.kwargs["args"][0]
    assert set(delivery) == {"__redis_key__"}
    assert delivery["__redis_key__"].startswith("dashboard:batch:")
    client.set.assert_called_once()
