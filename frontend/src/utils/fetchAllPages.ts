import api from '@/api/index'

/**
 * 循环拉取分页接口的全部数据。
 *
 * 仅用于必须在前端做全量聚合的场景（如机柜视图的分组统计、设备下拉选项）。
 * 普通列表页请使用 useCrudApi 的服务端分页，不要用本函数。
 *
 * @param url      接口地址，如 '/api/assets/devices/'
 * @param params   除分页外的查询参数
 * @param pageSize 每次请求的条数（后端上限 500）
 */
export const fetchAllPages = async (url: string, params: Record<string, any> = {}, pageSize = 500) => {
  const items: any[] = []
  let page = 1
  // 安全上限，避免接口异常时无限循环
  const maxPages = 200

  for (; page <= maxPages; page += 1) {
    const res = await api.get(url, { params: { ...params, page, page_size: pageSize } })
    const payload = res.data
    const batch: any[] = Array.isArray(payload) ? payload : payload?.results ?? []
    items.push(...batch)
    // 后端返回裸数组或没有下一页时结束
    if (Array.isArray(payload) || !payload?.next || batch.length === 0) break
  }

  return items
}
