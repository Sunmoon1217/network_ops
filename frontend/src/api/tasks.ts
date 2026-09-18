import api from './index'

/** 任务阶段（后端只读嵌套数组，随任务详情一起返回） */
export interface TaskStage {
  id: number
  stage_type: string
  stage_type_display: string
  status: string
  status_display: string
  error_message: string
  input_data: Record<string, any>
  output_data: Record<string, any>
  created_at: string
  started_at: string | null
  completed_at: string | null
  retry_count: number
}

/** 异步任务 */
export interface Task {
  id: number
  device: number
  device_hostname: string
  task_type: string
  task_type_display: string
  status: string
  status_display: string
  params: Record<string, any>
  result: Record<string, any> | null
  error_message: string
  progress: number
  created_at: string
  started_at: string | null
  completed_at: string | null
  stages: TaskStage[]
}

/** DRF 分页响应 */
export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

/** 设备下拉选项（设备接口每项至少含 id / hostname） */
export interface DeviceOption {
  id: number
  hostname: string
}

// 列表 / 详情
export const getTasks = (params?: Record<string, any>) =>
  api.get<Paginated<Task>>('/api/tasks/', { params })

export const getTask = (id: number) =>
  api.get<Task>(`/api/tasks/${id}/`)

// 创建任务（创建后后端立即投递异步任务）
export const createTask = (data: { device: number; task_type: string; params?: Record<string, any> }) =>
  api.post<Task>('/api/tasks/', data)

// 取消任务
export const cancelTask = (id: number) =>
  api.post<Task>(`/api/tasks/${id}/cancel/`)

// 设备下拉：契约要求一次取 500 条
export const getTaskDeviceOptions = () =>
  api.get<Paginated<DeviceOption>>('/api/assets/devices/', { params: { page_size: 500 } })
