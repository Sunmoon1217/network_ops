import axios from 'axios'
import type {
  DashboardCabinets,
  DashboardData,
  DashboardEnvelope,
  DashboardQuery,
  LinkSeries,
} from '@/types/dashboard'

/**
 * 大屏唯一供数入口：GET /api/dashboard/*（apps/analysis/api/dashboard.py）。
 *
 * - 大屏是无人值守的展示页，后端两个视图都显式 AllowAny：**前端不带 Token，也不做
 *   401 跳登录**，主站登录态过期不会影响大屏。
 * - 后端返回 {status, message, result} 包装（全站唯一例外），这里显式取 data.result。
 * - group=linechart 或 name=bandwidth-* 时，后端把最近 3 小时的 link_bandwidth
 *   样本聚合成一行一个时间点的 EAV 数据（list_value[0] = {time, data}）。
 * - 走同源相对路径：开发由 vite 代理 /api → :8000，生产由 nginx 反代。
 */
const client = axios.create({
  baseURL: '/api/dashboard/',
  timeout: 15_000,
  headers: { 'Content-Type': 'application/json' },
})

/** 按 panel / group / name 读取大屏指标行。 */
export const getDashboard = async (query: DashboardQuery = {}): Promise<DashboardData[]> => {
  const { data } = await client.get<DashboardEnvelope<DashboardData[]>>('', {
    params: {
      panel: query.panel || undefined,
      group: query.group || undefined,
      name: query.name || undefined,
    },
  })
  return data.result
}

/** 最近 3 小时的链路带宽折线（后端固定窗口，无 since/until 参数）。
 *
 * 返回 `{ rows, meta }`：`rows` 仍是旧的 EAV 行，`meta` 是脱敏的面板 / scope /
 * target label（随缓存一起下发），链路组件一次请求拿全。
 */
export const getLinkSeries = async (): Promise<LinkSeries> => {
  const { data } = await client.get<DashboardEnvelope<DashboardData[]>>('', {
    params: { panel: 'link', group: 'linechart' },
  })
  return { rows: data.result, meta: data.meta ?? null }
}

/** 单个时间点的最新采样，用于增量补点。 */
export const getLinkLatest = (time: string) =>
  getDashboard({ panel: 'link', group: 'linechart', name: `bandwidth-${time}` })

/** 机柜 U 位视图的最小字段（专用只读接口，不需要登录）。 */
export const getDashboardCabinets = async (): Promise<DashboardCabinets> => {
  const { data } = await client.get<DashboardEnvelope<DashboardCabinets>>('cabinets/')
  return data.result
}

export default client
