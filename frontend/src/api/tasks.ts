import api from './index'

import type {
  TaskStage, Task, Paginated, DeviceOption,
} from '@/types'

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
