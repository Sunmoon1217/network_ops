/** 大屏基础类型：路由、设备、接口、机柜、表格与配置行。 */
import 'vue-router'
import type { Component } from 'vue'
import type { Column } from 'element-plus/es/components/table-v2/src/types'

declare module 'vue-router' {
  interface routeMeta {
    title?: string
    viewConfig?: {
      layout?: string
      keepAlive?: boolean
      permission?: string[]
      hiddenInMenu?: boolean
      [key: string]: any
    }
  }
}

export interface RouteConfig {
  name?: string
  path?: string
  component?: Component | (() => Promise<Component>)
  meta?: {
    title?: string
    viewConfig?: Record<string, any>
  }
}

export interface Device {
  id: number
  hostname: string
  address: string
  username: string
  device_type: string
  idc?: string | null
  zone?: string | null
  connect_failed_at: string | null
}

export interface InterfaceConfig {
  id: number
  device_id: number
  device_name: string
  interface: string
  description: string | null
  shutdown?: string
}

export interface VirtualConfig {
  id: number
  device_id: number
  device_name: string
  name: string
  pool: string | null
}

export interface WideipConfig {
  id: number
  device_id: number
  device_name: string
  wideip: string
  type: string
}

export interface Config {
  id: number
  device: string
  config_text: string
  time: string
}

export interface DeviceInfo {
  name: string
  height: number
  model?: string
  vendor?: string
  ip?: string
}

export interface PositionInfo {
  position: string
  device: DeviceInfo
}

export interface RackInfo {
  name: string
  uCount: number
  detail: PositionInfo[]
}

export interface RackOptions {
  idc: []
  rowlist: []
  racklist: []
}

export interface Options {
  label: string
  value: string
}

export interface SearchFieldConfig {
  prop: string
  label: string
  type?: 'input' | 'select' | 'date'
  options?: Options[]
  placeholder?: string
  instantSearch?: boolean
  debounceMs?: number
}

export interface CursorPaginationState {
  cursor: string | null
  nextCursor: string | null
  prevCursor: string | null
  limit: number
  hasNext: boolean
  hasprev: boolean
}

export interface TableViewConfig {
  title: string
  apiUrl: string
  columns: Column<any>[]
  searchFields: SearchFieldConfig[]
  defaultLimit?: number
  actions?: {
    label: string
    onClick: (row: any) => void
  }[]
}
