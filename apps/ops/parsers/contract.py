"""解析器 / 模板 / Saver 之间的契约常量。

这里记录的是当前系统里**已确认存在**的映射断裂，供契约测试与映射清单接口共用，
避免两处各维护一份说明。修复某条缺口后请同步删除对应条目（测试会提醒）。

对账口径是**归一后**的键（``ops.mapping.canonical_key``）：别名键与其规范键
（``acl``/``rules`` → ``policies`` 等）视为同一语义，所以「模板产出别名、
Saver 注册规范键」不再算缺口。
"""

# 「Saver 消费了，但没有任何解析器产出该键（归一口径）」
# key 为 (device_type, key)，value 为原因说明
KNOWN_MISSING_PRODUCER: dict[tuple[str, str], str] = {
    # f5_ltm.ttp 里 snat 是 virtuals 的子 group，不是顶层键
    ("slb", "snat"): "snat 是 f5_ltm.ttp 中 virtuals 的子 group",
    ("slb", "snat_pools"): "同上",
}

# 「解析器产出了，但没有任何 Saver 消费」——按设备类型聚合的快照
KNOWN_UNCONSUMED_PRODUCTS: dict[str, set[str]] = {
    "firewall": {
        "hostname",
        "object_groups",
        "version",
        "vrouter",
        "vswitches",
        "zones",
    },
    # regions / topologies / monitors 尚无对应模型
    "gslb": {"monitors", "regions", "topologies"},
    "router": {"bgp", "hostname", "ospf", "ssh", "version"},
    "slb": {"account", "nodes", "servers", "service_groups", "virtual_server"},
    "switch": {
        "dhcp",
        "dhcp_pools",
        "domain_default",
        "domains",
        "hostname",
        "irf",
        "lldp",
        "radius",
        "roles",
        "ssh",
        "stp",
        "version",
    },
}
