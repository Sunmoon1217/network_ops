import api from './index'

import type {
  InspectionConfig,
  InspectionConfigPayload,
  InspectionDeviceMetric,
  InspectionDeviceSummary,
  InspectionDeviceTarget,
  InspectionDeviceTargetPayload,
  InspectionInterfaceMetric,
  InspectionRun,
  InspectionTarget,
  InspectionTargetPayload,
  Paginated,
} from '@/types'

// 巡检全局配置（单例）：时间点与每天采集时段，两类巡检共用
export const getInspectionConfig = () => api.get<InspectionConfig>('/api/analysis/inspection-config/')

export const updateInspectionConfig = (payload: Partial<InspectionConfigPayload>) =>
  api.patch<InspectionConfig>('/api/analysis/inspection-config/', payload)

// 设备巡检对象（CPU / 内存）：登录用户可读，operator / 超管可写
export const getInspectionDeviceTargets = (params?: Record<string, any>) =>
  api.get<Paginated<InspectionDeviceTarget>>('/api/analysis/inspection-device-targets/', { params })

export const createInspectionDeviceTarget = (payload: InspectionDeviceTargetPayload) =>
  api.post<InspectionDeviceTarget>('/api/analysis/inspection-device-targets/', payload)

export const updateInspectionDeviceTarget = (id: number, payload: Partial<InspectionDeviceTargetPayload>) =>
  api.patch<InspectionDeviceTarget>(`/api/analysis/inspection-device-targets/${id}/`, payload)

export const deleteInspectionDeviceTarget = (id: number) =>
  api.delete(`/api/analysis/inspection-device-targets/${id}/`)

// 巡检日指标（只读）：date 缺省取最新有数据的一天，host 模糊匹配
export const getInspectionDevices = (params?: Record<string, any>) =>
  api.get<Paginated<InspectionDeviceMetric>>('/api/analysis/inspection-devices/', { params })

// 当天概览：设备数、CPU / 内存均值与 CPU 峰值 TOP5
export const getInspectionSummary = (params?: Record<string, any>) =>
  api.get<InspectionDeviceSummary>('/api/analysis/inspection-devices/summary/', { params })

export const getInspectionInterfaces = (params?: Record<string, any>) =>
  api.get<Paginated<InspectionInterfaceMetric>>('/api/analysis/inspection-interfaces/', { params })

// 巡检批次（只读）：每日一条，用于展示最新采集结果与失败原因
export const getInspectionRuns = (params?: Record<string, any>) =>
  api.get<Paginated<InspectionRun>>('/api/analysis/inspection-runs/', { params })

// 带宽采集目标：读对所有登录用户开放，写限 operator 或超管
export const getInspectionTargets = (params?: Record<string, any>) =>
  api.get<Paginated<InspectionTarget>>('/api/analysis/inspection-targets/', { params })

export const createInspectionTarget = (payload: InspectionTargetPayload) =>
  api.post<InspectionTarget>('/api/analysis/inspection-targets/', payload)

export const updateInspectionTarget = (id: number, payload: Partial<InspectionTargetPayload>) =>
  api.patch<InspectionTarget>(`/api/analysis/inspection-targets/${id}/`, payload)

export const deleteInspectionTarget = (id: number) =>
  api.delete(`/api/analysis/inspection-targets/${id}/`)
