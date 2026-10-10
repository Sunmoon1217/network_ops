"""阿里云 SDK 客户端：按账户（生产/测试）获取预配置的 AcsClient。

配置来源：settings.ALIYUN_CONFIG——两套账号（prod/test），共用 region 与 endpoint。
凭据链路 *_FILE > 环境变量，与项目既有风格一致。
"""

from aliyunsdkcore.client import AcsClient
from django.conf import settings


def get_client(account: str = "prod") -> AcsClient:
    """按账户名获取预配置的 AcsClient。

    Args:
        account: "prod" | "test"
    """
    cfg = settings.ALIYUN_CONFIG
    acc = cfg["accounts"][account]
    client = AcsClient(
        acc["access_key_id"],
        acc["access_key_secret"],
        cfg["region"],
    )
    # 如果配了自定义 endpoint，为 4 个产品注册
    ep = cfg.get("endpoint")
    if ep:
        for product_code in ("Ecs", "Vpc", "Slb", "Sls"):
            client.add_endpoint(cfg["region"], product_code, ep)
    return client
