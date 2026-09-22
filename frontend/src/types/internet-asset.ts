/** 设备下拉项（只列 GSLB 设备）；与 api.ts 里任务下拉的 DeviceOption 字段不同，故单独命名 */
export interface GslbDeviceOption {
    id: number
    hostname: string
    device_type: string
    device_type_display?: string
    security_zone_name?: string
}

/** LTM 池成员节点，nested 为级联到的下层 LTM 虚拟服务器 */
export interface LtmMemberNode {
    name: string
    address: string
    port: string
    ip_port: string
    nested: LtmNode | null
    matched_ip_port: string
}

/** LTM 虚拟服务器节点（含池与池成员） */
export interface LtmNode {
    device: string
    name: string
    vs_address: string
    vs_port: string
    status: string
    pool: string
    pool_found: boolean
    rules: string[]
    members: LtmMemberNode[]
}

/** GTM 虚拟服务器（GTM 池成员解析到的下一跳） */
export interface GtmVServerNode {
    id: number
    name: string
    server_name: string
    ip_address: string
    port: string
    monitor: string
}

/** 链路解析三态：GTM VS 缺失 / 无对应 LTM VS / 完全解析 */
export type MemberStatus = 'vserver_not_found' | 'ltm_not_found' | 'resolved' | ''

/** GTM 池成员节点 */
export interface GtmMemberNode {
    server_name: string
    vs_name: string
    member_ref: string
    state: string
    order: number | null
    status: MemberStatus
    message: string
    vserver: GtmVServerNode | null
    ltm: LtmNode | null
    fallback_ip_port: string
}

/** GTM 池节点 */
export interface GtmPoolNode {
    name: string
    found: boolean
    lb_mode: string
    members: GtmMemberNode[]
}

/** WideIP 节点 */
export interface WideIpNode {
    id: number
    name: string
    rtype: string
    lb_mode: string
    pool_count: number
    pools: GtmPoolNode[]
}

/** 接口响应结构 */
export interface AnalysisResult {
    device: { id: number; hostname: string; device_type: string }
    wideips: WideIpNode[]
    /** 链路最后的 IP（原始写法）→ 负责人，后端按 ServerOwner 现查，不随分析缓存过期 */
    owners?: Record<string, string>
}

/**
 * 表格的一行：一条从域名到最终后端的完整链路。
 *
 * 列固定为 GTM 四列 + LTM 两级（LLB / SLB）各四列 + 说明。
 * 注意 LTM 的两级并非数据库外键关系：GTM 虚拟服务器的 ip:port 命中某个
 * LTM 虚拟服务器即为 LLB，LLB 池成员的 address:port 再命中一个 LTM 虚拟服务器
 * 即为 SLB，任何一跳匹配不上对应的四列就留空。
 */
export interface PathRow {
    key: string
    wideip: string
    rtype: string
    gtmIp: string
    gtmPort: string
    llbAddress: string
    llbPort: string
    /** 拼好的「地址:端口」，表格直接展示 */
    llbTarget: string
    llbRules: string
    llbMemberAddress: string
    llbMemberPort: string
    slbAddress: string
    slbPort: string
    slbTarget: string
    slbRules: string
    slbMemberAddress: string
    slbMemberPort: string
    /** 链路最后一跳的服务器「地址:端口」 */
    serverTarget: string
    owner: string
    note: string
}

/** 路径的一级：本级虚拟服务器 + 指向下一级的池成员（终点时为 null） */
export type LtmStep = [LtmNode, LtmMemberNode | null]

