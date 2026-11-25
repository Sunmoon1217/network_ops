"""阿里云 SDK 通道：账号装配、endpoint、ASAPI 出站调用与响应解包。

放在 core 是因为它提供的是「平台 ↔ 外部平台」的通道能力，多个域（采集 / 下发 / MCP）
都要用；它无状态，不注册 provider——调用方直接 ``from core.integrations.aliyun import ...``。
见 handbook/integrations.md「阿里云通道」。
"""

from .client import AliyunASAPI, aliyunapi, get_client
from .products import ecs_call, slb_call, sls_call, vpc_call
from .response import AsapiResponse, LoadBalancesResponse

__all__ = [
    "AliyunASAPI",
    "AsapiResponse",
    "LoadBalancesResponse",
    "aliyunapi",
    "ecs_call",
    "get_client",
    "slb_call",
    "sls_call",
    "vpc_call",
]
