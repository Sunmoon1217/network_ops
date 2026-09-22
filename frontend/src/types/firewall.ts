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
