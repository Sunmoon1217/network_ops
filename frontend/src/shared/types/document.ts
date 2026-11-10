/** 文档转换与 Dify 知识库推送（/api/docs/documents/，后端 docs 应用） */

/** 推送状态：converted=已转换待推送 / pushed=已推送 / push_failed=推送失败（可重推） */
export type DocPushStatus = 'converted' | 'pushed' | 'push_failed'

/** 文档列表条目（不含转换产物） */
export interface DocSummary {
  id: number
  name: string
  /** 源格式：txt/md/docx/html/pdf/xlsx/csv */
  source_format: string
  /** 产物格式：md/html（含图自包含 html）/pdf（直传无产物） */
  target_format: string
  has_images: boolean
  status: DocPushStatus
  /** 产物被人工编辑过（区别于纯转换产出） */
  edited: boolean
  /** 产物已改但知识库还是旧的，等手动重推（update 原地更新） */
  pending_sync: boolean
  latest_revision: number
  error: string
  dify_document_id: string
  dify_batch: string
  /** Dify 索引状态：waiting / indexing / completed / error */
  dify_indexing_status: string
  pushed_at: string | null
  created_by: string | null
  created_at: string
  updated_at: string
}

/** 文档详情（含转换产物，供查看 / 编辑） */
export interface DocDetail extends DocSummary {
  converted: string
}

/** 保存类接口（编辑产物 / 重转 / 回滚）响应：详情 + 落地的新版本号 */
export interface DocSaveResult extends DocDetail {
  revision: number
}

/** 版本历史条目（产物快照的元信息） */
export interface DocRevision {
  id: number
  revision: number
  note: string
  target_format: string
  has_images: boolean
  /** 该版本是人工编辑产物（true）还是转换产出（false） */
  edited: boolean
  created_by: string | null
  created_at: string
}

/** 单个版本（含产物全量快照） */
export interface DocRevisionDetail extends DocRevision {
  converted: string
}

/** 查看用渲染产物（md 已由后端渲染成 html；前端沙箱 iframe 展示） */
export interface DocPreview {
  html: string
  target_format: string
}
