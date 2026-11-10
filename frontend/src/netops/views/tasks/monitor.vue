<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { getCeleryStatus, getQueueStatus, getRedisStatus } from '@/api/monitor'
import StatCard from '@/components/StatCard.vue'
import DataTable from '@/components/DataTable.vue'
import DataColumn from '@/components/DataColumn.vue'
import { TABLE_KEYS } from '@/constants/tableKeys'
import type { CeleryStatus, QueueStatus, RedisStatus } from '@/types'

// ---------------------------------------------------------------------------
// 运行监控：Celery worker/任务（inspect）+ Redis 服务状态（INFO）+ 队列积压
// （queue_status），30s 轮询。全部只读——取消任务在「任务列表」、背压是生产者
// 自己的事，本页绝不干预。
// ---------------------------------------------------------------------------

const POLL_MS = 30_000
const activeTab = ref('celery')
const redisStatus = ref<RedisStatus | null>(null)
const celeryStatus = ref<CeleryStatus | null>(null)
const queueStatus = ref<QueueStatus | null>(null)
const redisError = ref('')
const celeryError = ref('')
const queueError = ref('')
let timer: ReturnType<typeof setInterval> | null = null
let polling = false

/**
 * 失败原因要能自证：只报「接口不可达」会把 401（未认证）/ 404（后端旧）/ 超时混成一种，
 * 排查时看不出到底是哪层出了问题。这里把 HTTP 状态与 DRF 的 detail 带出来。
 */
const describeError = (reason: unknown, label: string): string => {
  const err = reason as { response?: { status?: number; data?: { detail?: string } } } | undefined
  const status = err?.response?.status
  if (status === 401) return `${label}获取失败：401 未认证（token 失效或未带上，请重新登录）`
  if (status) {
    const detail = err?.response?.data?.detail
    return `${label}获取失败：HTTP ${status}${detail ? `（${detail}）` : ''}`
  }
  return `${label}获取失败：网络错误或超时（后端无响应）`
}

const fetchAll = async () => {
  if (polling) return
  polling = true
  const [redis, celery, queue] = await Promise.allSettled([getRedisStatus(), getCeleryStatus(), getQueueStatus()])
  if (redis.status === 'fulfilled') {
    redisStatus.value = redis.value.data
    redisError.value = ''
  } else {
    redisError.value = describeError(redis.reason, 'Redis 状态')
  }
  if (celery.status === 'fulfilled') {
    celeryStatus.value = celery.value.data
    celeryError.value = ''
  } else {
    celeryError.value = describeError(celery.reason, 'Celery 状态')
  }
  if (queue.status === 'fulfilled') {
    queueStatus.value = queue.value.data
    queueError.value = ''
  } else {
    queueError.value = describeError(queue.reason, '队列积压')
  }
  polling = false
}

onMounted(() => {
  fetchAll()
  timer = setInterval(fetchAll, POLL_MS)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})

const checkedAt = computed(() => {
  const stamp = celeryStatus.value?.checked_at ?? redisStatus.value?.checked_at
  return stamp ? new Date(stamp * 1000).toLocaleTimeString() : '--'
})

// --------------------------------- Redis ----------------------------------
const redisCards = computed(() => {
  const s = redisStatus.value
  if (!s?.redis_ok) return []
  const ratio = s.memory.used_ratio
  return [
    { label: '内存使用', value: s.memory.used_human ?? '--', color: ratio !== null && ratio > 0.8 ? 'var(--el-color-danger)' : undefined },
    { label: '内存使用率', value: ratio !== null ? `${(ratio * 100).toFixed(1)}%` : '不限制', color: ratio !== null && ratio > 0.8 ? 'var(--el-color-danger)' : undefined },
    { label: '连接客户端', value: s.clients.connected, color: s.clients.blocked ? 'var(--el-color-warning)' : undefined },
    { label: '每秒命令', value: s.stats.ops_per_sec },
    { label: '命中率', value: s.stats.hit_rate !== null ? `${(s.stats.hit_rate * 100).toFixed(1)}%` : '--' },
    { label: '键总数', value: s.keyspace.total_keys },
    { label: '运行时长', value: formatUptime(s.server.uptime_seconds) },
  ]
})

const redisDetails = computed(() => {
  const s = redisStatus.value
  if (!s?.redis_ok) return []
  return [
    ['版本', s.server.version ?? '--'],
    ['运行模式', s.server.mode ?? '--'],
    ['内存峰值', s.memory.peak_human ?? '--'],
    ['常驻内存(RSS)', s.memory.rss_human ?? '--'],
    ['碎片率', s.memory.fragmentation.toFixed(2)],
    ['阻塞客户端', String(s.clients.blocked)],
    ['累计命令', String(s.stats.total_commands)],
    ['逐出键', String(s.stats.evicted_keys)],
    ['过期键', String(s.stats.expired_keys)],
  ]
})

const formatUptime = (seconds: number) => {
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`
  return `${Math.floor(seconds / 86400)}d`
}

// --------------------------------- Celery ---------------------------------
const workerRows = computed(() => celeryStatus.value?.workers ?? [])
const activeRows = computed(() => celeryStatus.value?.active ?? [])
const pendingRows = computed(() => {
  const s = celeryStatus.value
  if (!s) return []
  return [
    ...s.reserved.map((t) => ({ ...t, segment: '已取走待执行' })),
    ...s.scheduled.map((t) => ({ ...t, segment: '延迟(eta)' })),
  ]
})

const celeryCards = computed(() => {
  const s = celeryStatus.value
  if (!s) return []
  return [
    { label: '在线 worker', value: s.workers.length, color: s.workers.length ? undefined : 'var(--el-color-danger)' },
    { label: '执行中', value: s.active.length },
    { label: '待执行', value: s.reserved.length + s.scheduled.length },
  ]
})

const formatTime = (stamp?: number) => (stamp ? new Date(stamp * 1000).toLocaleTimeString() : '--')

// --------------------------------- 队列积压 --------------------------------
const queueCards = computed(() => {
  const s = queueStatus.value
  if (!s?.redis_ok) return []
  const t = s.thresholds ?? {}
  const danger = 'var(--el-color-danger)'
  const mark = (v: number, limit?: number) => (limit !== undefined && v > limit ? danger : undefined)
  const lag = s.stream?.lag ?? s.stream?.xlen ?? 0
  return [
    { label: 'celery 队列', value: s.queues['celery'] ?? 0, color: mark(s.queues['celery'] ?? 0, t.max_queue) },
    { label: 'access_flow 队列', value: s.queues['access_flow'] ?? 0, color: mark(s.queues['access_flow'] ?? 0, t.max_queue) },
    { label: '执行中未确认', value: s.unacked, color: mark(s.unacked, t.max_unacked) },
    { label: 'Stream 积压', value: lag, color: mark(lag, t.max_stream_lag) },
    { label: '待确认(PEL)', value: s.stream?.pending ?? 0, color: mark(s.stream?.pending ?? 0, t.max_pending) },
  ]
})

const queueAlerts = computed(() => queueStatus.value?.alerts ?? [])
const topPending = computed(() => queueStatus.value?.stream?.top_pending ?? [])
</script>

<template>
  <div class="monitor-page">
    <div class="page-header">
      <span class="page-title">运行监控</span>
      <span class="page-refresh">刷新于 {{ checkedAt }} · 30s 自动刷新</span>
    </div>

    <el-tabs v-model="activeTab" class="monitor-tabs">
      <!-- ───────────────────────── Celery ───────────────────────── -->
      <el-tab-pane label="Celery" name="celery">
        <el-alert v-if="celeryError" :title="celeryError" type="warning" :closable="false" show-icon />
        <el-alert
          v-else-if="celeryStatus && !celeryStatus.ok"
          :title="celeryStatus.error ?? 'worker 无应答'"
          type="error"
          :closable="false"
          show-icon
        />
        <template v-else-if="celeryStatus">
          <div class="stat-row">
            <StatCard v-for="c in celeryCards" :key="c.label" :label="c.label" :value="c.value" :color="c.color" style="flex: 1; min-width: 140px;" />
          </div>

          <h4 class="section-title">Worker</h4>
          <DataTable :table-key="TABLE_KEYS.monitorWorkers" :data="workerRows">
            <DataColumn prop="name" label="Worker" :min-width="220" />
            <DataColumn prop="status" label="状态" :width="90" anchor>
              <template #default="{ row }">
                <el-tag type="success" size="small">{{ row.status }}</el-tag>
              </template>
            </DataColumn>
            <DataColumn prop="concurrency" label="并发" :width="90" />
            <DataColumn prop="processed" label="累计处理" :min-width="110" />
          </DataTable>

          <h4 class="section-title">执行中任务</h4>
          <DataTable :table-key="TABLE_KEYS.monitorActive" :data="activeRows">
            <DataColumn prop="name" label="任务" :min-width="220" />
            <DataColumn prop="worker" label="Worker" :min-width="160" />
            <DataColumn prop="started" label="开始时间" :width="110" anchor>
              <template #default="{ row }">{{ formatTime(row.started) }}</template>
            </DataColumn>
            <DataColumn prop="runtime" label="已跑" :width="90">
              <template #default="{ row }">{{ row.runtime != null ? `${row.runtime}s` : '--' }}</template>
            </DataColumn>
            <DataColumn prop="args" label="参数" :min-width="200" />
          </DataTable>

          <h4 class="section-title">待执行任务</h4>
          <DataTable :table-key="TABLE_KEYS.monitorPending" :data="pendingRows">
            <DataColumn prop="segment" label="来源" :width="130" anchor>
              <template #default="{ row }">
                <el-tag :type="row.segment === '延迟(eta)' ? 'info' : 'warning'" size="small">{{ row.segment }}</el-tag>
              </template>
            </DataColumn>
            <DataColumn prop="name" label="任务" :min-width="220" />
            <DataColumn prop="worker" label="Worker" :min-width="160" />
            <DataColumn prop="args" label="参数" :min-width="200" />
          </DataTable>
        </template>
      </el-tab-pane>

      <!-- ───────────────────────── Redis ───────────────────────── -->
      <el-tab-pane label="Redis" name="redis">
        <el-alert v-if="redisError" :title="redisError" type="warning" :closable="false" show-icon />
        <el-alert
          v-else-if="redisStatus && !redisStatus.redis_ok"
          :title="`Redis 不可达：${redisStatus.error ?? ''}`"
          type="error"
          :closable="false"
          show-icon
        />
        <template v-else-if="redisStatus">
          <div class="stat-row">
            <StatCard v-for="c in redisCards" :key="c.label" :label="c.label" :value="c.value" :color="c.color" style="flex: 1; min-width: 130px;" />
          </div>
          <h4 class="section-title">详细信息</h4>
          <el-descriptions :column="3" border size="small">
            <el-descriptions-item v-for="[label, value] in redisDetails" :key="label" :label="label">{{ value }}</el-descriptions-item>
          </el-descriptions>
        </template>
      </el-tab-pane>

      <!-- ─────────────────────── 队列积压 ─────────────────────── -->
      <el-tab-pane label="队列积压" name="queue">
        <el-alert v-if="queueError" :title="queueError" type="warning" :closable="false" show-icon />
        <el-alert
          v-else-if="queueStatus && !queueStatus.redis_ok"
          :title="`Redis 不可达，队列状态未知：${queueStatus.error ?? ''}`"
          type="error"
          :closable="false"
          show-icon
        />
        <template v-else-if="queueStatus">
          <div class="stat-row">
            <StatCard v-for="c in queueCards" :key="c.label" :label="c.label" :value="c.value" :color="c.color" style="flex: 1; min-width: 140px;" />
          </div>
          <div v-if="queueAlerts.length" class="alert-list">
            <el-alert
              v-for="(a, i) in queueAlerts"
              :key="i"
              :title="a.message"
              :type="a.level === 'critical' ? 'error' : 'warning'"
              :closable="false"
              show-icon
            />
          </div>
          <template v-if="topPending.length">
            <h4 class="section-title">重投最多的消息（疑似毒消息）</h4>
            <DataTable :table-key="TABLE_KEYS.monitorTopPending" :data="topPending">
              <DataColumn prop="id" label="消息 ID" :min-width="220" />
              <DataColumn prop="deliveries" label="重投次数" :width="110" anchor />
              <DataColumn prop="idle_ms" label="空闲" :width="110">
                <template #default="{ row }">{{ Math.round(row.idle_ms / 1000) }}s</template>
              </DataColumn>
            </DataTable>
          </template>
        </template>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.monitor-page { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
.page-header { display: flex; align-items: center; gap: 10px; }
.page-title { font-size: 18px; font-weight: 600; color: var(--el-text-color-primary); }
.page-refresh { margin-left: auto; font-size: 12px; color: var(--el-text-color-secondary); }
.stat-row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 8px; }
.section-title { margin: 14px 0 8px; font-size: 14px; color: var(--el-text-color-primary); }
.alert-list { display: flex; flex-direction: column; gap: 8px; margin: 8px 0; }
</style>
