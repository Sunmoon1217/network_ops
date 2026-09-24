/**
 * 负载均衡 / 域名解析关联链（`/api/lb-chain/*` 聚合接口的行结构）。
 *
 * 两页各把一条链压成一行：LTM 是 VS → 池 → 成员，GTM 是 WideIP → 池 → 虚拟服务器。
 * 展示约定：优先显示域名 / IP，`name` 类字段全部收进 hover 弹出。
 */

/** SLB 链上的 LTM 池（VS.pool 是名字，接口按 设备+池名 反查出来） */
export interface LtmChainPool {
  name: string
  mode: string
  monitors: string[]
}

/** LTM 池成员：address/port 优先展示，name 供 hover */
export interface LtmChainMember {
  name: string
  address: string
  port: string
}

/** SLB 关联链行：VS → 池 → 成员 */
export interface LtmChainRow {
  device: number
  device_hostname: string
  name: string
  vs_address: string
  vs_port: string
  protocol: string
  status: string
  snat_type: string
  persist: string
  /** VS 未配池或池记录缺失时为 null */
  pool: LtmChainPool | null
  members: LtmChainMember[]
}

/** GTM 池成员：address/port 来自 GtmVServer，找不到时 found=false、address 为 null */
export interface GtmChainMember {
  server: string
  vserver: string
  address: string | null
  port: string
  status: string
  found: boolean
}

/** GTM 池（wideip.pools 按 设备+池名 反查；池记录缺失时给空骨架） */
export interface GtmChainPool {
  name: string
  lb_mode: string
  fallback_ip: string
  ttl: number | null
  members: GtmChainMember[]
}

/** 域名解析关联链行：WideIP → 池 → 虚拟服务器 */
export interface GtmChainRow {
  device: number
  device_hostname: string
  name: string
  rtype: string
  lb_mode: string
  pools: GtmChainPool[]
}
