"""MCP 出口（/mcp）的接入层：路径判定 + 匿名限流 + 关闭时的明确 404。

**当前是匿名出口**：不验身份，能访问到 `/mcp` 就能调工具（只受 `DJANGO_ALLOWED_HOSTS`
与传输层 DNS rebinding 白名单约束）。总开关 `MCP_ENABLED=0` 时 `netops/asgi.py` 根本不建
MCP 子应用，本模块不参与任何请求。

**限流为什么按客户端 IP**：匿名出口没有比 IP 更细的身份可用。取值顺序
`X-Real-IP` → `X-Forwarded-For` 首跳 → ASGI `client`：nginx 侧 `X-Real-IP` 取
`$remote_addr`（客户端伪造不了），而 `$proxy_add_x_forwarded_for` 会保留客户端自带的前缀，
所以前者优先；不经 nginx 直连时两者都可伪造，此时限流只是「防手滑」，不是防护墙。

**开关关闭时必须自己回 404**：Django 侧对未知路径有 SPA 兜底（`views.vue_index`），`/mcp`
落到那里会拿到 200 + `index.html`，客户端侧表现为「JSON 解析失败 / 被 Vue 路由守卫拦住」，
排查成本极高（nginx 少配 location 时是同一个坑）。

**加鉴权时改哪里**：`_guard` 是唯一入口。验完身份把调用者写进 `scope["user"]`
（`mcp.server.auth.middleware.bearer_auth.AuthenticatedUser` + `mcp.server.auth.provider.AccessToken`），
MCP SDK 的 `_session_owners` 会自动拿它做会话归属绑定（别人拿着你的 `Mcp-Session-Id` 会被回
404），本模块之外不用改一行。会话 ID 本身**不是凭证**：它由 `initialize` 应答下发，SDK 只保证
「同一会话同一身份」，不负责「你是谁」。细节见 handbook/llmtools.md。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

import redis
from django.conf import settings

logger = logging.getLogger(__name__)

#: MCP 端点的路径前缀。与 ``netops/asgi.py`` 的分发、nginx 的 location、SDK 的默认路由一致。
BASE_PATH = "/mcp"

#: 限流键存活秒数：覆盖两个窗口，跨分钟边界时不会提前丢计数
_KEY_TTL = 120


def is_mcp_path(path: str) -> bool:
    """``/mcp`` 与 ``/mcp/...`` 归 MCP；``/mcpx``、``/api/mcp`` 不归。"""
    return path == BASE_PATH or path.startswith(BASE_PATH + "/")


def client_ip(scope: dict) -> str:
    """取调用方 IP（顺序见模块注释）；拿不到时返回 ``"unknown"`` 作为共享桶。"""
    headers: dict[str, str] = {}
    for name, value in scope.get("headers") or []:
        # 同名头只留第一个：与 nginx / ASGI 服务器一致，后到的重复头不覆盖
        headers.setdefault(name.decode("latin-1").lower(), value.decode("latin-1"))

    real = headers.get("x-real-ip", "").strip()
    if real:
        return real

    forwarded = headers.get("x-forwarded-for", "").split(",")[0].strip()
    if forwarded:
        return forwarded

    client = scope.get("client")
    return client[0] if client else "unknown"


def _over_limit(ip: str) -> bool:
    """固定窗口计数：本分钟该 IP 的请求数超过上限返回 True。

    Redis 故障**放行**（只告警）：限流是护栏不是业务，不该把出口搞挂。窗口用
    ``INCR`` + ``EXPIRE`` 两个命令实现，不用 Lua——允许跨分钟最多宽限一个窗口。
    """
    limit = settings.MCP_RATE_LIMIT_PER_MINUTE
    if limit <= 0:
        return False

    key = f"mcp:ratelimit:{ip}:{int(time.time() // 60)}"
    try:
        with redis.from_url(settings.REDIS_URL, socket_timeout=2, socket_connect_timeout=2) as client:
            count = client.incr(key)
            if count == 1:
                client.expire(key, _KEY_TTL)
    except redis.RedisError:
        logger.warning("MCP 限流计数失败，本次放行（Redis 不可用）", exc_info=True)
        return False

    if count > limit:
        logger.warning("MCP 出口限流：ip=%s 本分钟第 %d 次，上限 %d", ip, count, limit)
        return True
    return False


async def _send_json(send, status: int, detail: str) -> None:
    body = json.dumps({"detail": detail}, ensure_ascii=False).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json; charset=utf-8"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def send_disabled(send) -> None:
    """``MCP_ENABLED=0`` 时 `/mcp` 的应答（理由见模块注释：不能落到 SPA 兜底）。"""
    await _send_json(send, 404, "MCP 出口未启用（MCP_ENABLED=0）")


async def _guard(scope: dict, send) -> bool:
    """准入检查：True 表示放行，False 表示已经回好了错误响应（调用方直接 return）。"""
    ip = client_ip(scope)
    # redis 是同步客户端，丢线程池：事件循环里不许直接阻塞（MCP 一条连接可能挂很久）
    if await asyncio.to_thread(_over_limit, ip):
        await _send_json(send, 429, f"MCP 调用频率超限（每 IP 每分钟 {settings.MCP_RATE_LIMIT_PER_MINUTE} 次），请稍后重试")
        return False
    return True


class McpGuardMiddleware:
    """只拦 ``/mcp`` 前缀的 http 请求，其余 scope（lifespan / 别的路径）原样透传。

    包在 MCP 子应用外面而**不是**套在 `_dispatch` 外面：Django 侧的 `/api`、静态资源、
    admin 请求多得多，没必要每条都过一次关卡。
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not is_mcp_path(scope.get("path", "")):
            await self.app(scope, receive, send)
            return
        if not await _guard(scope, send):
            return
        await self.app(scope, receive, send)
