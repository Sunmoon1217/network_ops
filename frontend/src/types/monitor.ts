/** 队列积压巡检（/api/analysis/queue-status/，后端 analysis.queue_monitor 采集） */

/** PEL 里重投最多的消息（毒消息预警） */
export interface QueuePendingEntry {
  id: string
  /** 距上次投递的空闲毫秒数 */
  idle_ms: number
  /** 已投递次数（高 = 反复失败不 ack 的毒消息） */
  deliveries: number
}

/** 访问流 Stream 的积压画像 */
export interface QueueStreamStats {
  /** Stream 总条数（含已消费未 trim 的，不代表积压） */
  xlen: number
  /** 从未投递给消费者的真实积压；null = 组不存在或不可知 */
  lag: number | null
  /** 已投递未确认（PEL）条数 */
  pending: number
  /** 消费者组内成员数 */
  consumers: number
  /** 按重投次数排序的前几条 */
  top_pending: QueuePendingEntry[]
}

/** 巡检告警（只报警不干预） */
export interface QueueAlert {
  level: 'warning' | 'critical'
  code: string
  message: string
}

/** 一轮巡检的全貌 */
export interface QueueStatus {
  /** 采集时刻（epoch 秒） */
  checked_at: number
  redis_ok: boolean
  error: string | null
  /** celery 各队列的排队条数（键 = 队列名） */
  queues: Record<string, number>
  /** 执行中未确认任务数（worker 故障会滞留） */
  unacked: number
  stream: QueueStreamStats | null
  /** 消费者心跳距今秒数；null = 心跳缺失 */
  heartbeat_age: number | null
  /** 后端判定告警用的阈值（前端据此给数值标色） */
  thresholds: Record<string, number>
  alerts: QueueAlert[]
}
