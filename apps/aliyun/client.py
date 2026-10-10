"""阿里云 SDK 客户端：按账户（生产/测试）+ 产品获取预配置的 AcsClient。

配置来源：settings.ALIYUN_CONFIG——两套账号（prod/test），共用 region，
各产品 endpoint 由环境变量传递（不同产品 endpoint 不同）。
凭据链路 *_FILE > 环境变量，与项目既有风格一致。
"""

from typing import Literal

from aliyunsdkcore.client import AcsClient
from django.conf import settings


def get_client(account: Literal["prod", "test"] = "prod", product: str = "") -> AcsClient:
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
