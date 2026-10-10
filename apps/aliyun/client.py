"""阿里云 SDK 客户端：按账户（生产/测试）+ 产品获取预配置的 AcsClient。

配置来源：settings.ALIYUN_CONFIG——两套账号（prod/test），共用 region，
各产品 endpoint 由环境变量传递（不同产品 endpoint 不同）。
凭据链路 *_FILE > 环境变量，与项目既有风格一致。
"""

import json
from typing import cast

from aliyunsdkasapi.AsapiRequest import AsapiRequest
from aliyunsdkasapi.ASClient import ASClient
from aliyunsdkcore.acs_exception.exceptions import ClientException, ServerException
from aliyunsdkcore.client import AcsClient
from django.conf import settings


def get_client(account: str = "prod", product: str = "") -> AcsClient:
    """按账户名 + 产品代码获取预配置的 AcsClient。

    Args:
        account: "prod" | "test"
        product: 产品代码 "Ecs" / "Vpc" / "Slb" / "Sls"；为空则不绑定产品 endpoint
    """
    cfg = settings.ALIYUN_CONFIG
    acc = cfg["accounts"][account]
    client = AcsClient(
        acc["access_key_id"],
        acc["access_key_secret"],
        cfg["region"],
    )
    if product:
        ep = cfg["endpoints"].get(product)
        if ep:
            client.add_endpoint(cfg["region"], product, ep)
    return client


class AliyunASAPI:
    def __init__(self, account: str = "prod"):
        self.account = account
        self.client = ASClient(
            accessKeyId=settings.ALIYUN_CONFIG["accounts"][account]["access_key_id"],
            accessKeySecret=settings.ALIYUN_CONFIG["accounts"][account]["access_key_secret"],
            regionId=settings.ALIYUN_CONFIG["region"],
        )
        self.client.setSdkSource("network_ops")
        self.endpoint = settings.ALIYUN_CONFIG["endpoints"].get("Asapi")

    def call(self, product: str, version: str, action: str, params: dict, method: str = "GET") -> dict:
        request = AsapiRequest(product=product, version=version, action_name=action, asapi_gateway=self.endpoint)
        request.set_method(method)
        for key, value in params.items():
            request.add_query_param(key, value)
        try:
            response = self.client.do_action_with_exception(request)
            return json.loads(cast(str, response))
        except (ClientException, ServerException) as e:
            raise RuntimeError(f"阿里云 ASAPI 调用失败：{action}，错误信息：{e}") from e
