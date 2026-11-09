export interface Response<T = any> {
  status: number
  message: string
  result: T
}

export interface DashboardData {
  id: number
  panel: string
  group: string
  name: string
  value: string | number
  list_value: any[]
}
