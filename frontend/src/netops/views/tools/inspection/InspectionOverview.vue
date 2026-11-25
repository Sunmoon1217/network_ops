<script setup lang="ts">
import PageLayout from '@/components/PageLayout.vue'
import { getInspectionConfig, getInspectionDevices, getInspectionInterfaces, getInspectionRuns, getInspectionSummary } from '@/api/inspection'
import { Monitor, Connection } from '@element-plus/icons-vue'

import type { InspectionConfig, InspectionDeviceSummary, InspectionRun } from '@/types'

const router = useRouter()
const config = ref<InspectionConfig | null>(null)

const today = (() => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
})()

// —— 今日采集批次（每类只取一条） ——
const deviceRun = ref<InspectionRun | null>(null)
const lineRun = ref<InspectionRun | null>(null)
const runLoading = ref(false)

// —— 设备巡检概览 ——
const summary = ref<InspectionDeviceSummary | null>(null)
const deviceSummaryLoading = ref(false)

// —— 专线接口数 ——
const interfaceCount = ref(0)
const interfaceLoading = ref(false)

const pad = (v: number) => String(v).padStart(2, '0')
const scheduleHint = computed(() => {
  if (!config.value) return '加载中…'
  const t = `${pad(config.value.schedule_hour)}:${pad(config.value.schedule_minute)}`
  return `每日 ${t} · 采集 ${config.value.window_start.slice(0, 5)}–${config.value.window_end.slice(0, 5)}`
})

const fmtPct = (v: number | null) => (v == null ? '—' : `${v}%`)
const fmtTime = (v: string | null) => (v ? v.replace('T', ' ').slice(0, 19) : '—')

const cardStatus = (run: InspectionRun | null | undefined) => {
  if (!run) return { tag: 'info' as const, text: '未执行', hint: '今日尚无巡检结果' }
  if (run.status === 'success') return { tag: 'success' as const, text: '成功', hint: `${run.device_count} 设备 / ${run.interface_count} 接口` }
  return { tag: 'danger' as const, text: '失败', hint: run.error || '未知错误' }
}

const loadAll = async () => {
  runLoading.value = true
  deviceSummaryLoading.value = true
  interfaceLoading.value = true
  try {
    const runs = (await getInspectionRuns({ date: today, page_size: 10 })).data.results
    // 一个 run 同时包含设备和专线统计（由 write_inspection 写入），但 card 分开展示
    deviceRun.value = runs[0] ?? null
    lineRun.value = runs[0] ?? null
  } catch {
    deviceRun.value = null
    lineRun.value = null
  } finally {
    runLoading.value = false
  }
  try {
    summary.value = (await getInspectionSummary({ date: today })).data
  } catch {
    summary.value = null
  } finally {
    deviceSummaryLoading.value = false
  }
  try {
    interfaceCount.value = (await getInspectionInterfaces({ date: today, page_size: 1 })).data.count
  } catch {
    interfaceCount.value = 0
  } finally {
    interfaceLoading.value = false
  }
  try {
    config.value = (await getInspectionConfig()).data
  } catch {
    config.value = null
  }
}

onMounted(loadAll)

const goDetail = (kind: 'device' | 'line') =>
  router.push(kind === 'device' ? '/tools/inspection/device' : '/tools/inspection/line')

const deviceStatus = computed(() => cardStatus(deviceRun.value))
const lineStatus = computed(() => cardStatus(lineRun.value))
</script>

<template>
  <PageLayout title="巡检总览">
    <div class="overview">
      <div class="overview-head">
        <div class="head-left">
          <span class="head-date">今天 {{ today }}</span>
          <span class="head-sched">{{ scheduleHint }}</span>
        </div>
        <div class="head-right">
          <el-button type="primary" @click="router.push('/tools/inspection/config')">巡检配置</el-button>
        </div>
      </div>

      <div class="card-grid">
        <!-- 设备巡检 -->
        <div class="inspect-card" @click="goDetail('device')">
          <div class="card-head">
            <div class="card-title">
              <el-icon :size="18"><Monitor /></el-icon>
              <span>设备巡检</span>
            </div>
            <el-tag v-if="!runLoading" :type="deviceStatus.tag" effect="light">{{ deviceStatus.text }}</el-tag>
            <el-tag v-else type="info" effect="light">加载中…</el-tag>
          </div>

          <div class="card-metrics">
            <div class="metric">
              <span class="metric-label">设备数</span>
              <span class="metric-value">{{ summary?.device_count ?? 0 }}</span>
            </div>
            <div class="metric">
              <span class="metric-label">CPU 日均</span>
              <span class="metric-value">{{ fmtPct(summary?.cpu_avg ?? null) }}</span>
            </div>
            <div class="metric">
              <span class="metric-label">内存日均</span>
              <span class="metric-value">{{ fmtPct(summary?.memory_avg ?? null) }}</span>
            </div>
          </div>

          <div v-if="deviceRun?.finished_at" class="card-foot">完成于 {{ fmtTime(deviceRun.finished_at) }}</div>
          <div v-else class="card-foot muted">{{ deviceStatus.hint }}</div>

          <div class="card-action">查看详情 →</div>
        </div>

        <!-- 专线巡检 -->
        <div class="inspect-card" @click="goDetail('line')">
          <div class="card-head">
            <div class="card-title">
              <el-icon :size="18"><Connection /></el-icon>
              <span>专线巡检</span>
            </div>
            <el-tag v-if="!runLoading" :type="lineStatus.tag" effect="light">{{ lineStatus.text }}</el-tag>
            <el-tag v-else type="info" effect="light">加载中…</el-tag>
          </div>

          <div class="card-metrics">
            <div class="metric">
              <span class="metric-label">专线接口数</span>
              <span class="metric-value">{{ interfaceCount }}</span>
            </div>
            <div class="metric">
              <span class="metric-label">采集条数</span>
              <span class="metric-value">{{ lineRun?.interface_count ?? 0 }}</span>
            </div>
            <div class="metric">
              <span class="metric-label">完成时间</span>
              <span class="metric-value small">{{ fmtTime(lineRun?.finished_at ?? null) }}</span>
            </div>
          </div>

          <div v-if="!lineRun && !runLoading" class="card-foot muted">尚未有专线巡检数据</div>
          <div v-else-if="lineRun?.error" class="card-foot danger">{{ lineRun.error }}</div>
          <div v-else-if="lineRun?.finished_at" class="card-foot muted">巡检已落库</div>

          <div class="card-action">查看详情 →</div>
        </div>
      </div>

      <div class="config-hint">
        <el-alert
          type="info"
          :closable="false"
          show-icon
          :title="scheduleHint"
          description="时间点 / 采集时段 / 巡检对象均可在右侧「巡检配置」里调整，保存后下次 tick 自动生效。"
        />
      </div>
    </div>

  </PageLayout>
</template>

<style scoped>
.overview { display: flex; flex-direction: column; gap: 14px; }
.overview-head { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; }
.head-left { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.head-date { font-size: 15px; font-weight: 600; }
.head-sched { font-size: 12px; color: var(--el-text-color-secondary); }

.card-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }

.inspect-card {
  position: relative;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  padding: 18px 20px 16px;
  cursor: pointer;
  transition: box-shadow 0.18s, transform 0.18s, border-color 0.18s;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.inspect-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
  border-color: var(--el-color-primary-light-5);
  transform: translateY(-1px);
}
.card-head { display: flex; align-items: center; justify-content: space-between; }
.card-title { display: flex; align-items: center; gap: 8px; font-size: 15px; font-weight: 600; }

.card-metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.metric { display: flex; flex-direction: column; gap: 2px; }
.metric-label { font-size: 12px; color: var(--el-text-color-secondary); }
.metric-value { font-size: 20px; font-weight: 700; color: var(--el-text-color-primary); }
.metric-value.small { font-size: 13px; font-weight: 500; font-variant-numeric: tabular-nums; }

.card-foot { font-size: 12px; color: var(--el-text-color-primary); }
.card-foot.muted { color: var(--el-text-color-secondary); }
.card-foot.danger { color: var(--el-color-danger); }

.card-action {
  position: absolute;
  right: 18px;
  bottom: 12px;
  font-size: 12px;
  color: var(--el-color-primary);
  opacity: 0;
  transition: opacity 0.18s;
}
.inspect-card:hover .card-action { opacity: 1; }

.config-hint { margin-top: 4px; }

@media (max-width: 960px) {
  .card-grid { grid-template-columns: 1fr; }
}
</style>
