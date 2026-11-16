"""Celery 配置"""

import asyncio
import logging
import os

from celery import Celery
from celery.signals import worker_process_shutdown

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netops.settings")

app = Celery("netops")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

logger = logging.getLogger(__name__)


@worker_process_shutdown.connect
def _release_integrations(**_: object) -> None:
    """prefork 子进程退出时释放外部 client（Zabbix 的 session 此前泄漏到进程退出）。

    单例是**进程内**的：ASGI worker 与每个 Celery 子进程各持一份，所以两处都要挂释放钩子
    （ASGI 侧在 ``netops/asgi.py`` 的 lifespan，这里管 Celery 子进程）。

    释放本身是异步的（登出 + ``ClientSession.close()``），而 Celery 的收尾阶段没有运行中的
    事件循环——这里另起一个**只做释放**的短循环。任何异常都吞掉：收尾失败不该影响 worker 退出，
    ``release_all`` 内部也已经对单个 provider 失败做了隔离。
    """
    from core.integrations import release_all

    try:
        asyncio.run(release_all())
    except Exception:
        logger.exception("Celery 子进程释放集成实例失败")
