/** 软资产（T4）：由 GTM / LTM 配置行归并产出，接口只读。 */

/** 域名资产：一个 FQDN 一条，记录类型是行内多值。 */
export interface DomainAsset {
  id: number
  ci_id: string
  name: string
  fqdn: string
  rtypes: string[]
  ttl: number | null
  lb_mode: string
  pools: string[]
  fallback_ips: string[]
  vips: string[]
  devices: string[]
  inconsistent: boolean
  conflict_fields: string[]
  created_at: string
  updated_at: string
}

/** 负载均衡服务资产：一个 `VIP#port` 一条。 */
export interface LoadBalancerServiceAsset {
  id: number
  ci_id: string
  name: string
  asset_key: string
  vip: string
  port: string
  protocol: string
  pools: string[]
  member_count: number
  profiles: string[]
  rules: string[]
  devices: string[]
  status: string
  inconsistent: boolean
  conflict_fields: string[]
  created_at: string
  updated_at: string
}
