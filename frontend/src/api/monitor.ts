import api from './index'

import type { CeleryStatus, QueueMessageDetail, QueueStatus, RedisStatus } from '@/types'

// 监控接口单独放宽超时：celery-status 走 inspect 广播（最坏 5 × 1.5s），全局 10s 曾把它
// 掐死成「接口不可达」；其余两个是 Redis O(1) 命令，20s 只是同一组接口的统一裕量。
const MONITOR_TIMEOUT = { timeout: 20000 }

// 队列积压巡检（只读）：celery 队列 / 访问流 Stream / 消费者心跳，Home 页卡片轮询
export const getQueueStatus = () => api.get<QueueStatus>('/api/analysis/queue-status/', MONITOR_TIMEOUT)

// Stream 消息摘要（只读）：按消息 ID 看设备 / 载荷大小 / 组合数 / 前 N 条 key，运行监控「重投最多的消息」点开查看
export const getQueueMessage = (id: string, sample = 10) =>
  api.get<QueueMessageDetail>(`/api/analysis/queue-messages/${encodeURIComponent(id)}/`, { ...MONITOR_TIMEOUT, params: { sample } })

// Redis 服务状态（INFO 口径）：内存 / 连接 / 命中率 / 键空间，运行监控页轮询
export const getRedisStatus = () => api.get<RedisStatus>('/api/analysis/redis-status/', MONITOR_TIMEOUT)

// Celery worker 与任务（inspect 口径）：worker 名单 / 执行中 / 排队 / 延迟
export const getCeleryStatus = () => api.get<CeleryStatus>('/api/analysis/celery-status/', MONITOR_TIMEOUT)
