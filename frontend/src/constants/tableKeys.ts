/**
 * 表格 tableKey 注册表 —— 前端唯一的命名空间事实源（tableKey 约定文件）。
 *
 * 契约边界：后端 `/api/me/preferences/` 只是「按用户存取的不透明 JSON KV」，
 * 从不解析 key/value —— 所以约定全部在前端：**key 必须全局唯一、一页多表各占一条**，
 * 撞车的后果是两张表互相覆盖列宽（谁后写谁赢）。
 *
 * 命名：`<路由顶级域>.<路径余段>[.<表区分>]`，全小写、词沿用路由/文件名；
 * 单表页面不加后缀（`ipam.tags`），一页多表才加（`devices.baseline.snmp`），
 * 同页内嵌面板以前缀挂父页面（`config.policy.access-flows`）。
 *
 * 接入三件套（缺一不可，只写第一行等于没接）：
 *   1. `const { widthFor, onHeaderDragend } = useTablePrefs(TABLE_KEYS.xxx)`
 *   2. `<DataTable ... @header-dragend="onHeaderDragend">`
 *   3. `<el-table-column :width="widthFor('prop', 默认宽)">`（无 prop 的列必须给 `column-key`）
 *
 * 表格 key 一旦有用户存过就**不要直接改**：改名走下面的 `TABLE_KEY_RENAMES`
 * 登记旧 → 新，读端自动回退旧键，用户已存宽度不丢；迁移期结束后删掉条目即可。
 *
 * 标注「预留」的条目尚未接入页面，不产生任何数据，仅供接入时取用、防止另行起名撞车。
 */
export const TABLE_KEYS = {
  // ── devices ──────────────────────────────────────────────
  deviceList: 'devices.list', // 设备列表（/devices）
  deviceAccounts: 'devices.accounts', // 设备账号（/devices/accounts）
  deviceInterfaces: 'devices.interfaces', // 接口（/devices/interfaces）
  deviceVlans: 'devices.vlans', // VLAN（/devices/vlans）预留
  deviceParsers: 'devices.parsers', // 解析器模板（/devices/parsers）预留
  baselineSnmp: 'devices.baseline.snmp', // 基线 SNMP tab 预留
  baselineNtp: 'devices.baseline.ntp', // 基线 NTP tab 预留
  baselineSyslog: 'devices.baseline.syslog', // 基线 Syslog tab 预留

  // ── config ───────────────────────────────────────────────
  slbVirtualServers: 'config.slb.virtual-servers', // SLB 虚拟服务器 预留
  slbPools: 'config.slb.pools', // SLB 池 预留
  gslbWideips: 'config.gslb.wideips', // GSLB WideIP 预留
  gslbPools: 'config.gslb.pools', // GSLB 池 预留
  firewall: 'config.firewall', // NAT 规则（/config/firewall，单表）预留
  firewallPolicy: 'config.policy', // 安全策略（/config/policy 主表）预留
  accessFlows: 'config.policy.access-flows', // 访问流（policy 页内嵌面板）预留
  routingTable: 'config.routing-table', // 路由表 预留
  arpMac: 'config.arp-mac', // ARP/MAC 预留

  // ── ipam ─────────────────────────────────────────────────
  ipamSubnets: 'ipam.subnets', // 网段（/ipam/subnets）预留
  ipamAddresses: 'ipam.ip-addresses', // IP 地址 预留
  ipamTags: 'ipam.tags', // 标签 预留

  // ── tasks ────────────────────────────────────────────────
  taskList: 'tasks.list', // 任务列表 主表 预留
  taskStages: 'tasks.stages', // 任务详情展开的阶段表 预留

  // ── tools ────────────────────────────────────────────────
  dnsQuery: 'tools.dns-query', // DNS 查询·分组结果 预留
  dnsQueryBatch: 'tools.dns-query.batch', // DNS 查询·批量明细 预留
  internetAsset: 'tools.internet-asset', // 互联网资产路径 预留
  parserMapping: 'tools.parser-mapping.parsers', // 解析器映射主表 预留
  parserMappingMissing: 'tools.parser-mapping.missing-producers', // 契约缺口表 预留
  // 拓扑的 DeviceSelector 是弹窗选择列表，列宽偏好价值低，刻意不注册。
} as const

/**
 * 表格 key 改名登记：**旧 key → 新 key**。
 * 读端在新键还没有数据时回退读旧键，用户已存列宽不丢；首次拖动即整体迁移到新键。
 * 键值都必须是字符串；旧键故意不查 `TABLE_KEYS`（它已从注册表移除）。
 */
export const TABLE_KEY_RENAMES: Record<string, (typeof TABLE_KEYS)[keyof typeof TABLE_KEYS]> = {}
