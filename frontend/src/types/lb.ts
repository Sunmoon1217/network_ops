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
  /** 健康检查类型列表（池级 monitor，hover 弹出里展示） */
  monitor: string[]
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

/** GSLB 过滤下拉选项（GET /api/lb-chain/gslb/facets/） */
export interface GtmChainFacets {
  rtypes: string[]
  monitors: string[]
}

/**
 * 树形分级展示的行（el-table `tree-props` 的 `children` 结构），
 * 由上面的关联链行在页面里转换而来：顶级 = VS/WideIP，子级 = 池，孙级 = 成员。
 *
 * 两页共用一个结构、靠 `kind` 区分层级；各页用到的列字段不同
 * （LTM 用 `detail`，GTM 用 `rtype` / `mode` / `state`），没用到的留空即可。
 */
export interface LbTreeRow {
  /** row-key：链内唯一（设备 + 层级 + 名字/序号） */
  id: string
  kind: 'vs' | 'wideip' | 'pool' | 'member'
  /** 首列主显示：域名 / 地址#端口 / 池名（成员优先地址，回退名字） */
  label: string
  /** hover 弹出的多行说明——真正的 name 字段都收在这里；空数组不包 tooltip */
  tipLines: string[]
  /** 详情列（LTM：协议/SNAT/会话保持 或 池模式/监控，已拼成一行） */
  detail?: string
  /** 仅顶级行有值 */
  device?: string
  /** 记录类型（仅 GTM WideIP 行） */
  rtype?: string
  /** 负载模式（仅 GTM 的 WideIP / 池行） */
  mode?: string
  /** 成员链路状态：ok 正常 / disabled 停用 / lost 未找到上游虚拟服务器 */
  state?: 'ok' | 'disabled' | 'lost'
  children?: LbTreeRow[]
}
