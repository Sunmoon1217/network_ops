"""阿里云各产品 API 调用封装。

每个产品提供 call() 方法，封装：获取 client → 构造 request → 调用 → 解析 JSON。
请求参数通过 ``set_<ParamName>(value)`` 设置，RegionId 默认从 settings 注入。
"""

import json
from typing import Any

from .client import get_client


def _call(account: str, product: str, request_cls: type, **params) -> dict[str, Any]:
    """通用调用：实例化 request，设置参数，调用并返回解析后的 JSON 字典。

    Args:
        account: 账户名，"prod" 或 "test"
        product: 产品代码，"Ecs" / "Vpc" / "Slb" / "Sls"
        request_cls: 请求类（如 ``aliyunsdkecs.request.v20140526.DescribeInstancesRequest``）
        **params: 请求参数，key 对应 set_* 方法名（不含 set_ 前缀）。RegionId 未传时自动取 settings 中的值。

    Returns:
        API 响应的解析后 dict，包含 RequestId 与业务字段。
    """
    from django.conf import settings

    client = get_client(account, product)
    request = request_cls()

    # RegionId 自动注入（未显式传入时）
    if "RegionId" not in params:
        params["RegionId"] = settings.ALIYUN_CONFIG["region"]

    for key, value in params.items():
        setter = getattr(request, f"set_{key}", None)
        if setter is not None:
            setter(value)

    response = client.do_action_with_exception(request)
    if not response:
        raise RuntimeError(f"阿里云 {product} API 调用失败：{request_cls.__name__}，返回空响应")
    return json.loads(response)


# ---------------------------------------------------------------------------
# ECS（云服务器）
# ---------------------------------------------------------------------------


def ecs_call(account: str, request_cls: type, **params) -> dict[str, Any]:
    """调用 ECS API。

    用法::

        from aliyunsdkecs.request.v20140526 import DescribeInstancesRequest
        result = ecs_call("prod", DescribeInstancesRequest, PageSize=50)
    """
    return _call(account, "Ecs", request_cls, **params)


# ---------------------------------------------------------------------------
# VPC（含 VSwitch）
# ---------------------------------------------------------------------------


def vpc_call(account: str, request_cls: type, **params) -> dict[str, Any]:
    """调用 VPC API（含 VSwitch）。

    用法::

        from aliyunsdkvpc.request.v20160428 import DescribeVSwitchesRequest
        result = vpc_call("prod", DescribeVSwitchesRequest, PageSize=50)
    """
    return _call(account, "Vpc", request_cls, **params)


# ---------------------------------------------------------------------------
# SLB（负载均衡）
# ---------------------------------------------------------------------------


def slb_call(account: str, request_cls: type, **params) -> dict[str, Any]:
    """调用 SLB API。

    用法::

        from aliyunsdkslb.request.v20140515 import DescribeLoadBalancersRequest
        result = slb_call("prod", DescribeLoadBalancersRequest, PageSize=50)
    """
    return _call(account, "Slb", request_cls, **params)


# ---------------------------------------------------------------------------
# SLS（日志服务）
# ---------------------------------------------------------------------------


def sls_call(account: str, request_cls: type, **params) -> dict[str, Any]:
    """调用 SLS API。

    用法::

        from aliyunsdksls.request.v20191023 import CreateAppRequest
        result = sls_call("prod", CreateAppRequest, AppName="my-app")
    """
    return _call(account, "Sls", request_cls, **params)
