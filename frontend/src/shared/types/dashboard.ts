/** /api/dashboard/ 的响应包装（后端为兼容旧大屏保留的唯一例外）。 */
export interface Response<T = any> {
  status: number
  message: string
  result: T
}

export type DashboardEnvelope<T = DashboardData[]> = Response<T>

/** DashboardMetric 的一行；value 是标量，list_value 是采集器写入的对象数组。 */
export interface DashboardData {
  id: number
  panel: string
  group: string
  name: string
  value: number | string | null
  list_value: any[]
}

export interface DashboardQuery {
  panel?: string
  group?: string
  name?: string
}

/** 后端把 MetricSample 聚合出的一个时间点：scope → subject → 峰值使用率。 */
export interface LinkPoint {
  time: string
  data: Record<string, Record<string, number | null>>
}

/** devicestatus/<group>/cputop|memtop 的 top 项。 */
export interface DeviceTopItem {
  label: string
  value: number | null
}

/** inspection/device/list 的巡检设备行。 */
export interface InspectItem {
  name: string
  cpu_avg: number
  cpu_max: number
  memory_avg: number
  memory_max: number
}

/** itsmtask/case/<case_no> 的原始工单行（外部接口原字段透传）。 */
export interface TicketItem {
  case_no: string
  title: string
  shenqing: string
  zhixing?: string
  shijian?: string
  status?: string | null
}

/** /api/dashboard/cabinets/ 投影出的机柜字段。 */
export interface DashboardCabinet {
  id: number
  name: string
  row: string
  total_u: number
  status: string
  room_name: string
  datacenter_name: string
}

/** /api/dashboard/cabinets/ 投影出的设备 U 位字段。 */
export interface DashboardCabinetDevice {
  id: number
  hostname: string
  cabinet: number
  u_position: number
  height: number
  ip_address: string
  device_type: string
  device_type_display: string
}

export interface DashboardCabinets {
  cabinets: DashboardCabinet[]
  devices: DashboardCabinetDevice[]
}
