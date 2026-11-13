"""人工维护的服务器负责人（``ServerOwner``）。

唯一一张**没有 ``device`` 外键**的资产表：不从设备配置提取，全库唯一键是 ``ip``，
所以 ``scoped=False``、``order=("ip",)``。等它引用 ``IPAddress`` 对象时（见讨论中的
IPAM 关联），这里的 ``key``/``Filter`` 路径才需要跟着改。
"""

from assets import models
from assets.serializers import views as s
from llmtools.registry import EntitySpec, Filter

from ..nodes import NodeType

BUNDLE: dict[str, EntitySpec] = {
    NodeType.SERVER_OWNER: EntitySpec(
        node_type=NodeType.SERVER_OWNER,
        label="服务器负责人",
        model=models.ServerOwner,
        serializer=s.ServerOwnerSerializer,
        key="ip",
        summary=("hostname", "ip", "owner", "status"),
        filters={
            "keyword": Filter(("hostname", "ip", "owner")),
            "owner": Filter(("owner",)),
            "status": Filter(("status",), "exact"),
        },
        search=("ip", "hostname", "owner"),
        # 人工维护、无 device 外键，全库唯一键是 ip
        order=("ip",),
    ),
}
