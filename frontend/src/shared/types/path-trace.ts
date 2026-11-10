/** 路径追踪的单跳数据（一跳设备上的匹配结果与地址改写） */
export interface HopData {
    device_name: string
    device_id: number
    device_type: string
    zone: string
    vrf: string
    matched_policy: any
    matched_nat: any
    matched_route: any
    matched_vs: any
    action: string
    src_before: string
    src_after: string
    dst_before: string
    dst_after: string
    port_before: string
    port_after: string
}

/** 路径追踪结果：逐跳链路 + 终点信息 */
export interface TraceResult {
    hops: HopData[]
    final_src: string
    final_dst: string
    final_port: string
    blocked: boolean
    blocked_by: string
    lb_backend: any[]
    error: string
}
