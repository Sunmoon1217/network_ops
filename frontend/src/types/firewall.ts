/**
 * 防火墙/NAT 域的行类型。
 *
 * 后端 `PolicySerializer` 已把三个 M2M（源/目的 AddressBook、服务 Service）
 * 预先格式化成 `*_display` 字符串数组，前端表格直接消费、不再逐条展开。
 */

/** 访问策略列表行（`/api/assets/policies/`） */
export interface PolicyItem {
  id: number
  device: number
  device_hostname: string
  policy_id: string
  order: number
  name: string
  /** 归一后的动作：allow / deny（各厂商用词在入库时已统一） */
  action: 'allow' | 'deny'
  enabled: boolean
  /** M2M 主键（编辑表单用） */
  source_addresses: number[]
  destination_addresses: number[]
  services: number[]
  /** 展示串数组：地址形如 `name(10.0.0.0/24)`、服务形如 `tcp/80` */
  source_addresses_display: string[]
  destination_addresses_display: string[]
  services_display: string[]
  log: boolean
  description: string
  is_active: boolean
  created_at: string
}

/**
 * 访问流命中的单条策略上下文（`AccessFlow.contexts` 的值）。
 *
 * 键是 `"<device_pk>:<policy_pk>"`；值里冗余了设备与策略的展示信息，
 * 表格直接消费、不用反查。`action` 在入库时已归一为 allow / deny。
 */
export interface FlowContext {
  device_id: number
  hostname: string
  policy_pk: number
  /** 设备内的策略编号（与 policy_pk 不是一回事） */
  policy_id: string
  name: string
  action: 'allow' | 'deny'
  order: number
  enabled: boolean
}

/**
 * 访问流列表行（`/api/access-flows/`）。
 *
 * 键是九个字段（地址每侧 ip + prefix + range_end 三段，服务 protocol + port + port2
 * 三段），全非空参与唯一约束；`range_end` / `port2` 非该形态时为空串，
 * 任意（any）归一到 `0.0.0.0/0`。
 */
export interface AccessFlowItem {
  id: number
  src_ip: string
  src_prefix: number
  src_range_end: string
  dst_ip: string
  dst_prefix: number
  dst_range_end: string
  protocol: string
  port: string
  port2: string
  /** 命中上下文，键形如 `"3:17"`（device_pk:policy_pk） */
  contexts: Record<string, FlowContext>
  device_ids: number[]
  policy_ids: number[]
  created_at: string
  updated_at: string
}

/** 访问流面板的策略过滤条件（从策略列表「展开」带过来，id 是 Policy 主键） */
export interface AccessFlowPolicyFilter {
  id: number
  label: string
}

/** 一条访问流的审计结论（由 contexts 现算，见 AccessFlowPanel.auditFlags） */
export interface FlowAuditFlags {
  /** 同一设备有多条策略命中这条流（重复 / 多开） */
  dupDevices: boolean
  /** 同一行里 allow 与 deny 并存 */
  conflict: boolean
  devices: number
  policies: number
}
