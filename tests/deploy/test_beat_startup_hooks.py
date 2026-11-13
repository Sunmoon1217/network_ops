"""beat 启动钩子的脚本级契约：两条部署路径同构、四步齐全且都不阻塞启动。

守的是「删掉补投但测试全绿」：Celery 的 interval 条目首轮要等满一个周期，少了
``collect_dashboard`` 补投，beat 起来后前 10 分钟大屏没有工单 / SLB / 巡检；少了
调度自检，日志里缺条目时无法区分「调度没写」还是「code 卷没重铺」。
"""

from django.conf import settings

BEAT_SH = settings.BASE_DIR / "entrypoint" / "beat.sh"
DEPLOY_HOST_SH = settings.BASE_DIR / "scripts" / "deploy-host.sh"


def _beat_sh() -> str:
    return BEAT_SH.read_text(encoding="utf-8")


def _cmd_beat() -> str:
    """只取 cmd_beat 函数体，避免被别的服务函数里的同名命令干扰。"""
    text = DEPLOY_HOST_SH.read_text(encoding="utf-8")
    return text.split("cmd_beat() {")[1].split("\n}")[0]


def test_beat_entrypoint_runs_all_startup_hooks_in_order():
    text = _beat_sh()
    refresh = text.index("manage.py refresh_link_cache")
    collect = text.index("manage.py collect_dashboard")
    selfcheck = text.index("app.conf.beat_schedule")
    launch = text.index("exec celery -A netops beat")

    assert refresh < collect < selfcheck < launch


def test_deploy_host_cmd_beat_matches_entrypoint():
    block = _cmd_beat()

    assert "manage.py refresh_link_cache" in block
    assert "manage.py collect_dashboard" in block
    assert "app.conf.beat_schedule" in block
    assert "exec uv run celery -A netops beat" in block


def test_startup_hooks_never_block_beat():
    """set -e 下采集 / 自检失败必须有 || echo 兜底，否则 beat 起不来。

    调度自检的兜底在续行的下一行，所以把 hook 行与后一行拼起来一起看。
    """
    for text in (_beat_sh(), _cmd_beat()):
        lines = text.splitlines()
        for hook in ("manage.py refresh_link_cache", "manage.py collect_dashboard", "app.conf.beat_schedule"):
            index = next(i for i, row in enumerate(lines) if hook in row)
            assert "|| echo" in lines[index] + lines[index + 1], f"{hook} 没有失败兜底，会阻塞 beat 启动"
