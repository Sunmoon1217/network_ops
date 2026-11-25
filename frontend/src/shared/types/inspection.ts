/** 巡检全局配置（/api/analysis/inspection-config/）：时间点 + 每天采集时段 */
export interface InspectionConfig {
  schedule_hour: number
  schedule_minute: number
  /** HH:MM:SS */
  window_start: string
  /** HH:MM:SS */
  window_end: string
  last_dispatch_date: string | null
  updated_at: string
}

export interface InspectionConfigPayload {
  schedule_hour: number
  schedule_minute: number
  window_start: string
  window_end: string
}

/** 设备巡检对象（/api/analysis/inspection-device-targets/） */
export interface InspectionDeviceTarget {
  id: number
  host: string
  enabled: boolean
  updated_at: string
}

/** 设备巡检对象提交体 */
export interface InspectionDeviceTargetPayload {
  host: string
  enabled: boolean
}

/** 专线巡检带宽采集目标（/api/analysis/inspection-targets/） */
export interface InspectionTarget {
  id: number
  host: string
  ifname: string
  /** 监控项 ID 缓存；留空时采集器按主机名 + 接口名自动搜索 */
  itemids: string[]
  enabled: boolean
  updated_at: string
}

/** 采集目标的新建 / 编辑提交体 */
export interface InspectionTargetPayload {
  host: string
  ifname: string
  itemids: string[]
  enabled: boolean
}

/** 巡检批次（/api/analysis/inspection-runs/）：每日一条，数据新鲜度来源 */
export interface InspectionRun {
  id: number
  date: string
  status: 'success' | 'failed'
  device_count: number
  interface_count: number
  error: string
  started_at: string
  finished_at: string | null
}

/** 设备 CPU / 内存日指标（/api/analysis/inspection-devices/） */
export interface InspectionDeviceMetric {
  id: number
  date: string
  host: string
  cpu_avg: number | null
  cpu_max: number | null
  memory_avg: number | null
  memory_max: number | null
  updated_at: string
}

/** 接口带宽日指标（/api/analysis/inspection-interfaces/） */
export interface InspectionInterfaceMetric {
  id: number
  date: string
  host: string
  ifname: string
  in_bps_avg: number | null
  in_bps_max: number | null
  out_bps_avg: number | null
  out_bps_max: number | null
  in_usage_avg: number | null
  in_usage_max: number | null
  out_usage_avg: number | null
  out_usage_max: number | null
  updated_at: string
}

/** 设备日指标概览（inspection-devices/summary/） */
export interface InspectionDeviceSummary {
  date: string | null
  device_count: number
  cpu_avg: number | null
  memory_avg: number | null
  cpu_top: { name: string; cpu_max: number | null }[]
}
