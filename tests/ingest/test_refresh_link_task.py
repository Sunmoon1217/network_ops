"""链路缓存任务：全挂只记一条 error（不出 traceback），基础设施故障照旧抛。"""

import logging
from unittest.mock import patch

import pytest
import redis

from ingest import tasks as ingest_tasks
from ingest.collectors.link_cache import LinkCollectionError

ERROR = "全部 2 条链路采集失败 —— ipv4/zjbgp: ClientConnectorError: boom"


def test_all_failed_is_logged_once_without_raising(caplog):
    """外部源整体不可用：返回 status=failed + 一条 ERROR，不 raise（Celery 不打 traceback）。"""
    with caplog.at_level(logging.ERROR, logger=ingest_tasks.logger.name):
        with patch("ingest.collectors.link_cache.refresh_link_cache", side_effect=LinkCollectionError(ERROR)):
            result = ingest_tasks.refresh_link_cache_task()

    assert result == {"status": "failed", "error": ERROR}
    errors = [row for row in caplog.records if row.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "链路缓存刷新失败" in errors[0].getMessage()
    assert "ipv4/zjbgp" in errors[0].getMessage()


def test_infra_errors_still_raise():
    """Redis / 配置这类真实故障仍要抛：Celery 记 FAILURE，traceback 保留。"""
    with patch("ingest.collectors.link_cache.refresh_link_cache", side_effect=redis.RedisError("down")):
        with pytest.raises(redis.RedisError):
            ingest_tasks.refresh_link_cache_task()


def test_success_returns_summary_with_status():
    summary = {"points": 3, "targets": 2, "refreshed_at": "2026-11-11T10:00:00+00:00"}
    with patch("ingest.collectors.link_cache.refresh_link_cache", return_value=summary):
        result = ingest_tasks.refresh_link_cache_task()

    assert result == {"status": "success", **summary}
