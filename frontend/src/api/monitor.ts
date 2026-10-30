import api from './index'

import type { CeleryStatus, QueueStatus, RedisStatus } from '@/types'

// 队列积压巡检（只读）：celery 队列 / 访问流 Stream / 消费者心跳，Home 页卡片轮询
export const getQueueStatus = () => api.get<QueueStatus>('/api/analysis/queue-status/')

// Redis 服务状态（INFO 口径）：内存 / 连接 / 命中率 / 键空间，运行监控页轮询
export const getRedisStatus = () => api.get<RedisStatus>('/api/analysis/redis-status/')

// Celery worker 与任务（inspect 口径）：worker 名单 / 执行中 / 排队 / 延迟
export const getCeleryStatus = () => api.get<CeleryStatus>('/api/analysis/celery-status/')
