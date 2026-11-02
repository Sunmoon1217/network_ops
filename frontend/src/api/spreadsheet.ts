import api from './index'

import type { SpreadsheetData, SpreadsheetDetail, SpreadsheetRevision, SpreadsheetRevisionDetail, SpreadsheetSaveResult, SpreadsheetSummary } from '@/types'

// 通用表格（xlsx 编辑与历史）——上传/保存/恢复/删除是写操作（需操作员），其余只读
export const getSpreadsheets = () => api.get<{ results: SpreadsheetSummary[] }>('/api/sheets/')

// 上传 xlsx 建工作簿（解析成网格快照并落 v1 初始版本）
export const uploadSpreadsheet = (file: File, name?: string) => {
  const formData = new FormData()
  formData.append('file', file)
  if (name) formData.append('name', name)
  return api.post<SpreadsheetDetail>('/api/sheets/upload/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  })
}

export const getSpreadsheet = (id: number) => api.get<SpreadsheetDetail>(`/api/sheets/${id}/`)

// 保存编辑：后端 diff 出单元格级变更后落新版本；无改动返回 created=false
export const saveSpreadsheet = (id: number, data: SpreadsheetData, note?: string) =>
  api.put<SpreadsheetSaveResult>(`/api/sheets/${id}/`, { data, note })

export const deleteSpreadsheet = (id: number) => api.delete(`/api/sheets/${id}/`)

// 导出 xlsx：默认当前版本，revision 传历史版本号即导出该版本
export const exportSpreadsheet = (id: number, revision?: number) =>
  api.get(`/api/sheets/${id}/export/`, {
    params: revision === undefined ? undefined : { revision },
    responseType: 'blob',
    timeout: 30000,
  })

export const getSpreadsheetRevisions = (id: number) =>
  api.get<{ results: SpreadsheetRevision[] }>(`/api/sheets/${id}/revisions/`)

export const getSpreadsheetRevision = (id: number, revision: number) =>
  api.get<SpreadsheetRevisionDetail>(`/api/sheets/${id}/revisions/${revision}/`)

// 回滚到指定历史版本（以一次新保存落地，历史不被改写）
export const restoreSpreadsheetRevision = (id: number, revision: number, note?: string) =>
  api.post<SpreadsheetSaveResult>(`/api/sheets/${id}/revisions/${revision}/restore/`, note ? { note } : {})
