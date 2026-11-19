"""外部连接的健康状态：探活 → 写 `core.IntegrationHealth`（跨进程可读）。

client 实例是进程内的；admin / MCP 所在进程看不到采集进程持有什么实例，所以健康状态必须
外化。这里只做两件事：``probe_all``（beat 周期任务调用）与 ``snapshot``（API 供数）。
探活方式统一为「provider 能 acquire 即 ok」——具体怎么连由 provider 决定，core 不懂业务。
设计见 ``handbook/design/external-clients.md`` §健康状态必须外化。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from django.utils import timezone

from core.models import IntegrationHealth

logger = logging.getLogger(__name__)

STATUS_OK = "ok"
STATUS_DOWN = "down"
STATUS_UNKNOWN = "unknown"


async def _probe(provider: Any) -> tuple[str, str]:
    """取一次实例即判定连通，拿到后立刻释放（避免长期占用 worker 的 session）。"""
    try:
        await provider.acquire()
    except Exception as exc:  # noqa: BLE001 —— 任何异常都记 down，且不能中断其它 provider
        return STATUS_DOWN, f"{type(exc).__name__}: {exc}"
    try:
        await provider.release()
    except Exception:  # noqa: BLE001 —— 释放失败不影响「连得上」这个判定
        logger.exception("释放集成实例失败（探活后）")
    return STATUS_OK, ""


def probe_all() -> int:
    """逐 provider 探活并 upsert 健康行，返回探活数量。"""
    from core.integrations import get_provider, registered

    count = 0
    for key in registered():
        system, instance = key
        status, error = asyncio.run(_probe(get_provider(system, instance)))
        IntegrationHealth.objects.update_or_create(
            system=system,
            instance=instance,
            defaults={"status": status, "checked_at": timezone.now(), "error": error},
        )
        count += 1
    return count


def snapshot() -> list[dict[str, Any]]:
    """已注册 provider 与健康行的并集（API 用）。

    没有健康行的实例按 ``unknown`` 返回——「没探过」不等于「挂了」；注册表里有、但库里
    有行的实例（比如该进程没注册某域）也照样列出，便于发现跨进程差异。
    """
    from core.integrations import describe_all

    descriptions = {(item["system"], item["instance"]): item for item in describe_all()}
    rows = {(row.system, row.instance): row for row in IntegrationHealth.objects.all()}

    items: list[dict[str, Any]] = []
    for system, instance in sorted(set(descriptions) | set(rows)):
        row = rows.get((system, instance))
        items.append(
            {
                "system": system,
                "instance": instance,
                "description": descriptions.get((system, instance), {}),
                "status": row.status if row else STATUS_UNKNOWN,
                "checked_at": row.checked_at if row else None,
                "error": row.error if row else "",
            }
        )
    return items
