export interface ZabbixConfig {
  url: string
  token?: string
  username?: string
  password?: string
}

// 定义 Zabbix JSON-RPC 请求结构
export interface ZabbixRequest {
  jsonrpc: '2.0'
  method: string
  params?: any
  id: number | string
  auth?: string | null
}

// 定义 Zabbix 响应结构
export interface ZabbixResponse<T = any> {
  jsonrpc: '2.0'
  result?: T
  error?: {
    code: number
    message: string
    data: string
  }
  id: number | string
}

export interface ZabbixGroup {
  groupid: string
  name: string
}

export interface ZabbixHost {
  hostid: string
  host: string
  name?: string
}

export interface ZabbixItem {
  itemid: string
  value_type: string
  name?: string
  key_?: string
  hostid?: string
  lastvalue?: string
  hosts?: Array<{
    hostid: string
    host: string
    name?: string
  }>
}

export interface ZabbixHistoryPoint {
  itemid: string
  value: string
  clock: string
}

export interface TimeValuePoint {
  // time: number
  value: number
}

export interface InterfaceMaxData {
  timeList: number[]
  maxData: number[]
}

export interface ZabbixProblem {
  eventid: string
  acknowledged?: string
  objectid?: string
  name?: string
}

export interface ZabbixTrigger {
  triggerids: string
  status: string
}
