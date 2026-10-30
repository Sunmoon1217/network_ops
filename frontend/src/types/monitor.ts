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

// ---------------------------------------------------------------------------
// 运行监控（/api/analysis/redis-status/ 与 /api/analysis/celery-status/，
// 后端 analysis.redis_monitor / analysis.celery_monitor 采集）
// ---------------------------------------------------------------------------

/** Redis 服务状态（INFO 口径） */
export interface RedisServerInfo {
  version: string | null
  mode: string | null
  uptime_seconds: number
}

export interface RedisMemoryInfo {
  used_bytes: number
  used_human: string | null
  peak_human: string | null
  rss_human: string | null
  fragmentation: number
  maxmemory_human: string | null
  /** 内存使用率 0~1；maxmemory=0（不限制）时为 null */
  used_ratio: number | null
}

export interface RedisClientsInfo {
  connected: number
  blocked: number
  maxclients: number
}

export interface RedisStatsInfo {
  ops_per_sec: number
  total_commands: number
  hits: number
  misses: number
  /** 命中率 0~1；hits/misses 皆 0（没跑过读）时为 null */
  hit_rate: number | null
  evicted_keys: number
  expired_keys: number
}

export interface RedisKeyspaceInfo {
  dbs: Record<string, { keys: number; expires: number }>
  total_keys: number
  dbsize: number
}

/** 一轮 Redis 服务状态采集的全貌 */
export interface RedisStatus {
  checked_at: number
  redis_ok: boolean
  error: string | null
  server: RedisServerInfo
  memory: RedisMemoryInfo
  clients: RedisClientsInfo
  stats: RedisStatsInfo
  keyspace: RedisKeyspaceInfo
}

/** Celery worker 行（ping 应答者 + stats 的容量信息） */
export interface CeleryWorkerInfo {
  name: string
  concurrency: number
  processed: number
  status: string
}

/** Celery 任务行（active / reserved / scheduled 共用；started/eta 按段出现） */
export interface CeleryTaskInfo {
  id: string
  name: string
  args: string
  kwargs: string
  worker: string
  /** 开始执行时刻（epoch 秒，active 段） */
  started?: number
  /** 已跑秒数（active 段） */
  runtime?: number | null
  /** 计划执行时刻（scheduled 段） */
  eta?: string | null
}

/** 一轮 Celery worker/任务采集的全貌 */
export interface CeleryStatus {
  checked_at: number
  ok: boolean
  error: string | null
  workers: CeleryWorkerInfo[]
  active: CeleryTaskInfo[]
  reserved: CeleryTaskInfo[]
  scheduled: CeleryTaskInfo[]
}
