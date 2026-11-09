// src/types/device.ts
// 设备相关类型定义

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
