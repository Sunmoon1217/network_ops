"""消费者 / 项目日志的可观测性契约（docker logs 全黑的两层根因，2026-11 排障结论）。

「容器部署消费者后 docker logs 没有日志」= 两层原因叠加，锁的就是这两条修复：

1. **stdout 块缓冲**：stdout 接 docker logs 的管道时 Python 是块缓冲（约 8KB），
   `self.stdout.write` 的「访问流消费启动」短行一直卡在缓冲区里、进程退出冲刷才
   突然冒出来 → consumer.sh 的启动命令必须无缓冲（`python -u`，或 PYTHONUNBUFFERED=1）。
2. **INFO 被 lastResort 丢弃**：正常运行期唯一的日志是 `logger.info("已入库 …")`，而项目
   此前没有任何 LOGGING 配置——root 无 handler 时 Python 走 lastResort 兜底、级别
   **WARNING**，INFO 被静默丢弃（报错的 logger.exception 走 stderr 反而可见，故表象是
   「平时全黑、出错才有日志」）→ settings.LOGGING 必须给项目 logger 挂 console handler。

详见 entrypoint/consumer.sh 顶部注释与 netops/settings/base.py 的 LOGGING 段。
"""

import io
import logging

from django.conf import settings

CONSUMER_SH = settings.BASE_DIR / "entrypoint" / "consumer.sh"
# apps/ 是顶层包，logger 名即 getLogger(__name__) 的应用名前缀（与 base.py 的 LOGGING 对账）
PROJECT_LOGGERS = ("analysis", "assets", "cloud", "core", "docs", "ingest", "netops")


def test_consumer_start_command_is_unbuffered():
    """consumer.sh 的启动命令必须无缓冲：否则 docker logs 到进程退出才见日志。"""
    text = CONSUMER_SH.read_text(encoding="utf-8")
    assert "python -u manage.py" in text, "consumer.sh 需用 `python -u`（或 PYTHONUNBUFFERED）关掉 stdout 块缓冲"


def test_project_loggers_configured_at_info_with_stderr_handler():
    """settings.LOGGING 给全部项目 logger 挂 stderr console handler（INFO）。

    level=INFO 是关键：没有自己的 handler 就落回 root 的 lastResort（WARNING），
    INFO 还是会被丢。propagate 必须保持 True（caplog 靠传播到 root 抓记录，
    tests/assets/test_device_group.py 的「跳过解析」断言即依赖它；root 无自有
    handler，传播上去不会重复打印）。
    """
    loggers = settings.LOGGING["loggers"]
    handler = settings.LOGGING["handlers"]["console"]
    assert handler["class"] == "logging.StreamHandler"
    assert handler["stream"] == "ext://sys.stderr"  # 行缓冲，docker logs 实时可见
    for name in PROJECT_LOGGERS:
        assert loggers[name]["handlers"] == ["console"]
        assert loggers[name]["level"] == "INFO"
        assert loggers[name]["propagate"] is True


def test_info_record_is_emitted_by_console_handler():
    """端到端：`logger.info("已入库 …")` 真的被 console handler 发出来（格式化 + 写流）。

    不用 capfd 断言 stderr：handler 的 stream 在 django setup（dictConfig）时就绑定，
    落到 pytest 全局捕获的替身对象上、绕过 fixture 级 capfd（实测 capfd.readouterr()
    为空而 pytest 报告的「Captured stderr call」里明明有）——把 handler 的 stream 临时
    换成 StringIO 直接验证 handler 这一段，输出落在 stderr 由上一条测试锁。
    """
    console = logging.getLogger("analysis").handlers[0]
    buffer, original = io.StringIO(), console.stream
    console.stream = buffer
    try:
        logging.getLogger("analysis.contract-test").info("已入库 contract: +1 ~0")
    finally:
        console.stream = original
    assert "已入库 contract" in buffer.getvalue()


def test_info_record_still_propagates_to_root(caplog):
    """传播不许断：caplog / 将来挂到 root 的 handler 要能收到项目 logger 的记录。"""
    logging.getLogger("analysis.contract-test").info("已入库 propagate: +1 ~0")
    assert "已入库 propagate" in caplog.text
