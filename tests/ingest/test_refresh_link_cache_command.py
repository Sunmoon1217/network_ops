"""``refresh_link_cache`` 管理命令：--check 只校验、默认动作写缓存。"""

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command

from ingest.collectors import link_cache


def test_check_only_validates_config():
    out = StringIO()
    call_command("refresh_link_cache", "--check", stdout=out)

    text = out.getvalue()
    assert "配置校验通过" in text
    assert "链路: 10" in text


def test_refresh_command_writes_cache():
    out = StringIO()
    summary = {"points": 1, "targets": 2, "refreshed_at": "2026-11-11T10:00:00+00:00"}
    with patch.object(link_cache, "refresh_link_cache", return_value=summary) as mocked:
        call_command("refresh_link_cache", stdout=out)

    mocked.assert_called_once()
    assert "缓存已刷新" in out.getvalue()
