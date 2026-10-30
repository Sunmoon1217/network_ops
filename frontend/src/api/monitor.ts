import api from './index'

import type { QueueStatus } from '@/types'

// 队列积压巡检（只读）：celery 队列 / 访问流 Stream / 消费者心跳，Home 页卡片轮询
export const getQueueStatus = () => api.get<QueueStatus>('/api/analysis/queue-status/')
