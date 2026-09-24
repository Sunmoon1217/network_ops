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
  /** VS 的 profile / iRule 名字列表（一级行单独展示） */
  profiles: string[]
  rules: string[]
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
  /** 成员的调度权重信息（入库形态为 int；手工/旧模板缺省时为 null） */
  order: number | null
  ratio: number | null
  /** 成员级健康检查（单值） */
  monitor: string
  /** 所属 server 的数据中心（vs 缺失时也给得出） */
  datacenter: string
}

/** GTM 池（wideip.pools 按 设备+池名 反查；池记录缺失时给空骨架） */
export interface GtmChainPool {
  name: string
  lb_mode: string
  alternate_mode: string
  fallback_mode: string
  fallback_ip: string
  ttl: number | null
  /** 池级健康检查类型列表（hover 弹出与监控列共用） */
  monitor: string[]
  members: GtmChainMember[]
}

/**
 * SLB 扁平宽表行：**以链最深层为行粒度**（有成员每成员一行，池无成员则池行，
 * 无池则 VS 行），VS 与池的字段整条下填、融合成一张大表。
 * 与树形模式是两套列——扁平不是「去缩进」，而是 join 展开。
 */
export interface LtmFlatRow {
  /** 行唯一：链根 + 层级标记 + 序号 */
  id: string
  kind: 'vs' | 'pool' | 'member'
  /** 主标识：成员地址#端口；回退行是池名 / VS地址#端口 */
  label: string
  /** hover：成员 name 与链路归属 */
  tipLines: string[]
  device: string
  vsLabel: string
  vsName: string
  protocol: string
  snat: string
  persist: string
  profiles: string[]
  rules: string[]
  poolName: string
  poolMode: string
  poolMonitors: string
}

/**
 * GSLB 扁平宽表行：粒度规则同 LtmFlatRow——
 * wideip 字段 + 池字段 + 成员字段三段全部下填到叶子行。
 */
export interface GtmFlatRow {
  id: string
  kind: 'wideip' | 'pool' | 'member'
  label: string
  tipLines: string[]
  device: string
  /** wideip 段 */
  domain: string
  rtype: string
  wideAlgo: string
  /** 池段 */
  poolName: string
  poolAlgo: string
  fallback: string
  ttl: string
  poolMonitor: string
  /** 池级调度权重 = 池内成员取值集合去重（与树形二级池行同义），与成员自身值分列 */
  poolOrder: string
  poolRatio: string
  /** 成员段（回退行为空串/ '-'） */
  order: string
  ratio: string
  memberMonitor: string
  datacenter: string
  state?: 'ok' | 'disabled' | 'lost'
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
  /** hover 弹出的多行说明——真正的 name 字段与次要信息收在这里；空数组不包 tooltip */
  tipLines: string[]
  /** 仅顶级行有值 */
  device?: string
  /** 以下五个 + vsName/poolName 仅 SLB 一级 VS 行填充（GTM 行用 rtype/mode/state） */
  vsName?: string
  protocol?: string
  poolName?: string
  profiles?: string[]
  persist?: string
  rules?: string[]
  /** 记录类型（仅 GTM WideIP 行） */
  rtype?: string
  /** 负载算法（GTM：一级 lb_mode；二级 池 lb_mode / alternate_mode） */
  mode?: string
  /** fallback 策略（仅 GTM 二级池行，已拼好 mode(ip)） */
  fallback?: string
  /** 健康检查（GTM 二级池级列表 join / 三级成员单值） */
  monitor?: string
  /** 调度权重（GTM 二级 = 池内成员取值集合去重 / 三级 = 成员自身值） */
  order?: string
  ratio?: string
  /** 数据中心（仅 GTM 三级成员行，来自其所属 server） */
  datacenter?: string
  /** 成员链路状态：ok 正常 / disabled 停用 / lost 未找到上游虚拟服务器 */
  state?: 'ok' | 'disabled' | 'lost'
  children?: LbTreeRow[]
}
