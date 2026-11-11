"""``manage.py collect_dashboard``：默认投两个源、可指定源、``--sync`` 走本进程。"""

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from ingest import tasks as ingest_tasks

SUMMARY = {"run": {"status": "success", "error": ""}, "metrics": 1, "samples": 2, "cases": 0}


def test_default_enqueues_both_sources():
    with patch.object(ingest_tasks, "collect_dashboard") as collect:
        collect.delay.return_value.id = "fake-id"
        call_command("collect_dashboard", stdout=StringIO())

    assert [call.args[0] for call in collect.delay.call_args_list] == ["zabbix", "autotask"]


def test_single_source_only_enqueues_that_one():
    with patch.object(ingest_tasks, "collect_dashboard") as collect:
        collect.delay.return_value.id = "fake-id"
        call_command("collect_dashboard", "autotask", stdout=StringIO())

    collect.delay.assert_called_once_with("autotask")


def test_sync_runs_inline():
    with patch.object(ingest_tasks, "collect_dashboard", return_value=SUMMARY) as collect:
        call_command("collect_dashboard", "zabbix", "--sync", stdout=StringIO())

    collect.assert_called_once_with("zabbix")
    collect.delay.assert_not_called()


def test_sync_non_success_run_raises():
    payload = {"run": {"status": "failed", "error": "采集炸了"}, "metrics": 0, "samples": 0, "cases": 0}
    with patch.object(ingest_tasks, "collect_dashboard", return_value=payload):
        with pytest.raises(CommandError, match="采集炸了"):
            call_command("collect_dashboard", "zabbix", "--sync", stdout=StringIO())


def test_unknown_source_rejected():
    with pytest.raises(CommandError, match="未知数据源"):
        call_command("collect_dashboard", "nope", stdout=StringIO())
