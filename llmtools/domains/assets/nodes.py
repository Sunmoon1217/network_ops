"""资产域的节点类型标识（``specs/`` 与 ``edges.py`` 的公共词汇表）。

刻意放在域包根目录、且**零 import**：实体声明（``specs/*.py``）与关系边（``edges.py``）
都只依赖这里，谁也不依赖谁，拆文件不会产生循环 import。
"""


class NodeType:
    """资产域的节点类型标识。

    **刻意不用 ``models.TextChoices``**：``Enum`` 的 ``__hash__`` 按成员名取哈希，
    于是 ``NodeType.DEVICE`` 和 ``"device"`` 相等却哈希不同，作为 ``dict`` 键查不到。
    这里要的是普通字符串常量。
    """

    DEVICE = "device"
    DEVICE_GROUP = "device_group"
    INTERFACE = "interface"
    VLAN = "vlan"
    VRF = "vrf"
    ROUTE = "route"
    SUBNET = "subnet"
    IP_ADDRESS = "ip_address"
    ARP_MAC = "arp_mac"
    LTM_VIRTUAL_SERVER = "ltm_virtual_server"
    LTM_POOL = "ltm_pool"
    LTM_POOL_MEMBER = "ltm_pool_member"
    LTM_PROFILE = "ltm_profile"
    LTM_IRULE = "ltm_irule"
    LTM_SNAT = "ltm_snat"
    LTM_PERSIST = "ltm_persist"
    GTM_DATACENTER = "gtm_datacenter"
    GTM_WIDEIP = "gtm_wideip"
    GTM_POOL = "gtm_pool"
    GTM_SERVER = "gtm_server"
    GTM_VSERVER = "gtm_vserver"
    ADDRESS_BOOK = "address_book"
    SERVICE = "service"
    POLICY = "policy"
    NAT_RULE = "nat_rule"
    SERVER_OWNER = "server_owner"


__all__ = ["NodeType"]
