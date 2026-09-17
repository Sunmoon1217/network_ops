"""解析器 / 模板 / Saver 之间的契约常量。

这里记录的是当前系统里**已确认存在**的映射断裂，供契约测试与映射清单接口共用，
避免两处各维护一份说明。修复某条缺口后请同步删除对应条目（测试会提醒）。
"""

# 「Saver 消费了，但没有任何解析器产出该键」
# key 为 (device_type, key)，value 为原因说明
KNOWN_MISSING_PRODUCER: dict[tuple[str, str], str] = {
    # hillstone 产出 addresses / cisco 产出 acl，两者都没有 address_books
    ("firewall", "address_books"): "模板产出 addresses（hillstone），无 address_books",
    # 模板产出 acl（cisco）/ rules（hillstone），都不是 policies
    ("firewall", "policies"): "模板产出 acl（cisco）/ rules（hillstone）",
    # f5_ltm.ttp 里 snat 是 virtuals 的子 group，不是顶层键
    ("slb", "snat"): "snat 是 f5_ltm.ttp 中 virtuals 的子 group",
    ("slb", "snat_pools"): "同上",
    # 模板只产出 vpn_instances
    ("router", "vrfs"): "模板产出 vpn_instances",
    ("switch", "vrfs"): "模板产出 vpn_instances",
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
