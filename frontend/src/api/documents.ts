import api from './index'

import type { DocDetail, DocPreview, DocRevision, DocRevisionDetail, DocSaveResult, DocSummary } from '@/types'

// 文档转换与 Dify 知识库推送（/api/docs/documents/）——上传/编辑/重转/推送/回滚/删除是写操作（需操作员），其余只读
export const getDocuments = () => api.get<{ results: DocSummary[] }>('/api/docs/documents/')

// 上传转换：file 主文档 + attachments 图片附件（md/html 引用的本地图片随附）；转换失败 400 不落记录
export const uploadDocument = (file: File, attachments?: File[]) => {
  const formData = new FormData()
  formData.append('file', file)
  attachments?.forEach((a) => formData.append('attachments', a))
  return api.post<DocDetail>('/api/docs/documents/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  })
}

export const getDocument = (id: number) => api.get<DocDetail>(`/api/docs/documents/${id}/`)

// 编辑转换产物：落新版本快照；已推送文档标记待同步（pdf 直传无产物，后端拒）
export const updateDocument = (id: number, converted: string, note?: string) =>
  api.put<DocSaveResult>(`/api/docs/documents/${id}/`, { converted, note })

// 替换源文件重新转换（人工修改的产物会被覆盖，旧产物仍在版本历史里可回滚）
export const reconvertDocument = (id: number, file: File, attachments?: File[], note?: string) => {
  const formData = new FormData()
  formData.append('file', file)
  attachments?.forEach((a) => formData.append('attachments', a))
  if (note) formData.append('note', note)
  return api.post<DocSaveResult>(`/api/docs/documents/${id}/reconvert/`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  })
}

export const deleteDocument = (id: number) => api.delete(`/api/docs/documents/${id}/`)

// 查看用渲染产物（md 已渲染成 html，沙箱 iframe 展示）
export const previewDocument = (id: number) => api.get<DocPreview>(`/api/docs/documents/${id}/preview/`)

// 源文件下载（docx/pdf 等原文件留档）
export const downloadDocument = (id: number) =>
  api.get(`/api/docs/documents/${id}/download/`, { responseType: 'blob', timeout: 30000 })

// 推送 Dify：未推送 create；已推送且待同步时 update 原地更新（不产生重复文档）
export const pushDocument = (id: number) => api.post<DocDetail>(`/api/docs/documents/${id}/push/`)

// 从 Dify 同步索引进度（waiting / indexing / completed / error）
export const syncDocumentStatus = (id: number) => api.get<DocDetail>(`/api/docs/documents/${id}/status/`)

export const getDocumentRevisions = (id: number) => api.get<{ results: DocRevision[] }>(`/api/docs/documents/${id}/revisions/`)

export const getDocumentRevision = (id: number, revision: number) => api.get<DocRevisionDetail>(`/api/docs/documents/${id}/revisions/${revision}/`)

// 回滚到指定版本（以一次新版本落地，历史不被改写）
export const restoreDocumentRevision = (id: number, revision: number, note?: string) =>
  api.post<DocSaveResult>(`/api/docs/documents/${id}/revisions/${revision}/restore/`, note ? { note } : {})
