<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getDashboard } from '@/api/dashboard'
import type { InspectItem } from '@dashboard/types'
import { useInterval } from '@dashboard/utils/timer'

const EMPTY = '暂无数据'
const items = ref<InspectItem[]>([])
const loadError = ref('')

const num = (value: unknown): number | null =>
  typeof value === 'number' && Number.isFinite(value) ? value : null

const summary = computed(() => {
  if (!items.value.length) return { cpuAvg: EMPTY, memAvg: EMPTY, cpuMax: EMPTY }
  const cpuAvg = items.value.reduce((sum, item) => sum + (num(item.cpu_avg) ?? 0), 0) / items.value.length
  const memAvg = items.value.reduce((sum, item) => sum + (num(item.memory_avg) ?? 0), 0) / items.value.length
  const cpuMax = Math.max(...items.value.map((item) => num(item.cpu_max) ?? 0))
  return { cpuAvg: `${cpuAvg.toFixed(1)}%`, memAvg: `${memAvg.toFixed(1)}%`, cpuMax: `${cpuMax}%` }
})

const topCpu = computed(() =>
  [...items.value]
    .sort((a, b) => (num(b.cpu_max) ?? 0) - (num(a.cpu_max) ?? 0))
    .slice(0, 5),
)

const fetchData = async () => {
  try {
    // 后端只写 inspection/device/list（autotask 的设备巡检结果），没有完成率指标
    const rows = await getDashboard({ panel: 'inspection', group: 'device' })
    items.value = (rows.find((row) => row.name === 'list')?.list_value ?? []) as InspectItem[]
    loadError.value = ''
  } catch (error) {
    console.error('[dashboard] 巡检数据获取失败:', error)
    loadError.value = '巡检数据获取失败'
  }
}

const { start } = useInterval(fetchData, 5 * 60 * 1000, true)

onMounted(() => {
  start()
})
</script>

<template>
  <div class="container">
    <div class="summary">
      <h4>巡检结果概览</h4>
      <p v-if="loadError" class="error">{{ loadError }}</p>
      <p v-else>已巡检设备 {{ items.length }} 台 · CPU 平均 {{ summary.cpuAvg }} · 内存平均 {{ summary.memAvg }}</p>
    </div>
    <div class="items">
      <article class="item-card">
        <div class="item-head"><h5>CPU 峰值</h5><span class="status-badge ok">{{ summary.cpuMax }}</span></div>
        <p class="item-summary">全部巡检设备中的 CPU 最高使用率</p>
      </article>
      <article class="item-card">
        <div class="item-head"><h5>CPU TOP5</h5><span class="status-badge ok">{{ topCpu.length }} 台</span></div>
        <div v-if="!topCpu.length" class="empty">暂无巡检数据</div>
        <div v-for="item in topCpu" :key="item.name" class="top-row">
          <span :title="item.name">{{ item.name }}</span>
          <strong>{{ num(item.cpu_max) ?? '--' }}%</strong>
        </div>
      </article>
    </div>
  </div>
</template>

<style scoped>
.container { height: 100%; display: grid; grid-template-rows: auto 1fr; gap: 8px; }

.summary {
  border: 1px solid rgba(111, 244, 255, 0.16);
  border-radius: 12px;
  padding: 8px 10px;
  background: rgba(255, 255, 255, 0.03);
}

.summary h4 { margin: 0; font-size: 14px; color: #eaf6ff; }
.summary p { margin: 6px 0 0; font-size: 12px; color: #b6d7ef; }
.summary p.error { color: #ffb7c3; }

.items { display: grid; grid-template-columns: 0.8fr 1.2fr; gap: 8px; min-height: 0; }

.item-card {
  border: 1px solid rgba(111, 244, 255, 0.16);
  border-radius: 12px;
  padding: 10px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.045), rgba(255, 255, 255, 0.02));
  overflow: hidden;
}

.item-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.item-head h5 { margin: 0; font-size: 13px; color: #ecf7ff; }

.status-badge {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  color: #9af3cb;
  border: 1px solid rgba(61, 222, 159, 0.4);
  background: rgba(61, 222, 159, 0.12);
}

.item-summary { margin: 8px 0 0; font-size: 12px; line-height: 1.5; color: #cfe8ff; }
.empty { margin-top: 12px; font-size: 12px; color: #88a9c8; }

.top-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 5px 0;
  font-size: 12px;
  color: #d7ecfb;
  border-bottom: 1px solid rgba(111, 244, 255, 0.1);
}

.top-row span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.top-row strong { color: #6ff4ff; }
</style>
