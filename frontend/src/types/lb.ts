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
  /** wideip 级权重：f5_gtm wideip 组里每个池自己的 order/ratio（老数据没有 → null） */
  order?: number | null
  ratio?: number | null
  members: GtmChainMember[]
}

/**
 * SLB 扁平宽表行：**以链最深层为行粒度**（有成员每成员一行，池无成员则池行，
 * 无池则 VS 行），VS 与池的字段整条下填、融合成一张大表。
 * 与明细模式（根行 + 展开面板）是两套列——扁平不是「去缩进」，而是 join 展开。
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
  /** 池级调度权重 = 池内成员取值集合去重（与展开面板的池行同义），与成员自身值分列 */
  poolOrder: string
  poolRatio: string
  /** 成员段（回退行为空串/ '-'）；server / vs 与明细面板一致拆成两列 */
  server: string
  vs: string
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
 * 主表根行（一级 = VS / WideIP）：**只放根自身的配置字段**——
 * 池 / 成员明细全部收进 `panel`，由 `type="expand"` 列渲染成展开面板，
 * 不再借主表列展示（两页主表列增删/隐藏都不影响展开内容，反之亦然）。
 *
 * 两页共用一个结构、靠 `kind` 区分根类型；各页用到的字段不同
 * （SLB 用 vsName/protocol/…，GTM 用 rtype/mode），没用到的留空即可。
 */
export interface LbRootRow {
  /** row-key：链根唯一（设备 + 层级 + 名字） */
  id: string
  kind: 'vs' | 'wideip'
  /** 首列主显示：VS 地址#端口（透明 VS 回退名字）/ 域名 */
  label: string
  /** hover 弹出的多行说明——次要信息收在这里；空数组不包 tooltip */
  tipLines: string[]
  device: string
  /** SLB 一级 VS 行字段 */
  vsName?: string
  protocol?: string
  poolName?: string
  profiles?: string[]
  persist?: string
  rules?: string[]
  /** 记录类型（GTM WideIP 行） */
  rtype?: string
  /** 负载算法（GTM WideIP 行的 lb_mode） */
  mode?: string
  /** 展开面板 = **pool 表**（无表头、格子自带字段名；池行再展开一层才是 member 表） */
  panel?: LbPoolRow[]
}

/**
 * pool 表行（根行的展开面板里，`el-table` + `show-header=false`）：
 * 字段与主表列**完全无关**——每格自带「字段名：」前缀，所以表头可以整个砍掉。
 * `panel` 是该池的 **member 表**：严格依赖关系，成员只挂在自己的池行下。
 * 两页共用一个结构（SLB 只用 label/algo/monitor，GTM 用全量），没用到的留空。
 */
export interface LbPoolRow {
  /** pool 表内唯一（链根 + 池名） */
  id: string
  /** 池名（pool 表首列） */
  label: string
  /** 负载算法/模式（SLB = pool.mode；GTM = 池 lb_mode / alternate_mode） */
  algo?: string
  /** fallback 策略（仅 GTM，已拼好 mode(ip)） */
  fallback?: string
  /** TTL（仅 GTM） */
  ttl?: string
  /** 健康检查（池级列表 join） */
  monitor?: string
  /** wideip 级权重（pool_order / pool_ratio；老数据没有 → order 空、ratio 兜底 1） */
  order?: string
  ratio?: string
  /** 展开面板 = member 表（空数组时面板显示占位文案） */
  panel?: LbMemberRow[]
}

/**
 * member 表行（pool 行的展开面板里，同样无表头、格子自带字段名）：
 * SLB 只用 name/address，GTM 用全量（名称已拆成 server / vs 两列）。
 */
export interface LbMemberRow {
  /** member 表内唯一（链根 + 池名 + 序号） */
  id: string
  /** 名称：节点名（仅 SLB）；没有名称时回退成地址 */
  name?: string
  /** 服务器名（仅 GTM，原「名称」列的 server 半段） */
  server?: string
  /** 虚拟服务器名（仅 GTM，原「名称」列的 vs 半段） */
  vs?: string
  /** 地址#端口；与名称重复时该格不渲染 */
  address?: string
  order?: string
  ratio?: string
  monitor?: string
  /** 所属 server 的数据中心（仅 GTM） */
  datacenter?: string
  /** 成员链路状态：ok 正常 / disabled 停用 / lost 未找到上游虚拟服务器（仅 GTM） */
  state?: 'ok' | 'disabled' | 'lost'
}
