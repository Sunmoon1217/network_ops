<script setup lang="ts">
import { onMounted, ref } from 'vue'
import GaugeCharts from '@dashboard/ui/GaugeCharts.vue'
import DeviceTopList from './DeviceTopList.vue'
import { getDashboard } from '@/api/dashboard'
import type { DashboardData, DeviceTopItem } from '@dashboard/types'
import { useInterval } from '@dashboard/utils/timer'

const GROUPS = [
  { name: '交换机', group: 'switch' },
  { name: '路由器', group: 'router' },
  { name: '防火墙', group: 'firewall' },
  { name: '负载均衡', group: 'loadbalance' },
  { name: 'DNS', group: 'dns' },
] as const

const EMPTY = '暂无数据'

interface DeviceCard {
  name: string
  status: string
  statusClass: 'ok' | 'warn' | 'muted'
  gaugeData: Array<{ name: string; value: number }>
  deviceCount: string
  problemCount: string
  cpuMax: string
  memMax: string
  top: { cpu: DeviceTopItem[]; memory: DeviceTopItem[] }
}

const toNumber = (value: unknown): number | null => {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  return null
}

const emptyCard = (name: string): DeviceCard => ({
  name,
  status: EMPTY,
  statusClass: 'muted',
  gaugeData: [
    { name: 'CPU', value: 0 },
    { name: '内存', value: 0 },
  ],
  deviceCount: EMPTY,
  problemCount: EMPTY,
  cpuMax: EMPTY,
  memMax: EMPTY,
  top: { cpu: [], memory: [] },
})

const cards = ref<DeviceCard[]>(GROUPS.map((item) => emptyCard(item.name)))
const loadError = ref('')

const rowOf = (rows: DashboardData[], group: string, name: string) =>
  rows.find((item) => item.group === group && item.name === name)

const topList = (rows: DashboardData[], group: string, name: string): DeviceTopItem[] =>
  (rowOf(rows, group, name)?.list_value ?? []) as DeviceTopItem[]

const fetchCards = async () => {
  try {
    // 采集器写入 devicestatus/<group>/{count,problems,cpumax,cputop,memmax,memtop}
    const rows = await getDashboard({ panel: 'devicestatus' })
    cards.value = GROUPS.map(({ name, group }) => {
      const card = emptyCard(name)
      if (!rows.some((item) => item.group === group)) return card

      const count = toNumber(rowOf(rows, group, 'count')?.value)
      const problems = rowOf(rows, group, 'problems')?.list_value
      const cpuMax = toNumber(rowOf(rows, group, 'cpumax')?.value)
      const memMax = toNumber(rowOf(rows, group, 'memmax')?.value)

      card.deviceCount = count === null ? EMPTY : String(count)
      card.problemCount = problems ? String(problems.length) : EMPTY
      card.cpuMax = cpuMax === null ? EMPTY : `${cpuMax}%`
      card.memMax = memMax === null ? EMPTY : `${memMax}%`
      card.gaugeData = [
        { name: 'CPU', value: cpuMax ?? 0 },
        { name: '内存', value: memMax ?? 0 },
      ]
      card.top = {
        cpu: topList(rows, group, 'cputop'),
        memory: topList(rows, group, 'memtop'),
      }
      card.status = problems?.length ? '存在告警' : '运行正常'
      card.statusClass = problems?.length ? 'warn' : 'ok'
      return card
    })
    loadError.value = ''
  } catch (error) {
    console.error('[dashboard] 设备状态获取失败:', error)
    loadError.value = '设备状态获取失败'
  }
}

const { start } = useInterval(fetchCards, 5 * 60 * 1000, true)

onMounted(() => {
  start()
})
</script>

<template>
  <div class="container">
    <div v-for="card in cards" :key="card.name" class="item">
      <div class="item-head">
        <h4>{{ card.name }}</h4>
        <span class="status-badge" :class="card.statusClass">{{ card.status }}</span>
      </div>
      <div class="chart-wrap">
        <GaugeCharts :data="card.gaugeData" />
        <div class="toplist-popover">
          <DeviceTopList :data="card.top" />
        </div>
      </div>
      <div class="metrics">
        <div class="metric-row"><span>设备数</span><strong>{{ card.deviceCount }}</strong></div>
        <div class="metric-row"><span>告警</span><strong :class="card.statusClass">{{ card.problemCount }}</strong></div>
        <div class="metric-row"><span>CPU 峰值</span><strong>{{ card.cpuMax }}</strong></div>
        <div class="metric-row"><span>内存峰值</span><strong>{{ card.memMax }}</strong></div>
      </div>
    </div>
    <p v-if="loadError" class="load-error">{{ loadError }}</p>
  </div>
</template>

<style scoped>
.container {
  position: relative;
  height: 100%;
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0.5em;
}

.item {
  border: 1px solid var(--line);
  border-radius: 16px;
  display: grid;
  grid-template-rows: auto minmax(90px, 1fr) auto;
  min-height: 0;
  padding: 10px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.02));
}

.item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.item-head h4 {
  margin: 0;
  font-size: 14px;
  color: #eaf6ff;
}

.status-badge {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  border: 1px solid transparent;
}

.status-badge.ok { color: #9af3cb; border-color: rgba(61, 222, 159, 0.4); background: rgba(61, 222, 159, 0.12); }
.status-badge.warn { color: #ffe49a; border-color: rgba(255, 211, 94, 0.4); background: rgba(255, 211, 94, 0.12); }
.status-badge.muted { color: #9fb6cc; border-color: rgba(159, 182, 204, 0.3); background: rgba(159, 182, 204, 0.1); }

.chart-wrap {
  position: relative;
  height: 100%;
  min-height: 0;
}

.toplist-popover {
  display: none;
  position: absolute;
  z-index: 5;
  top: 0;
  left: 0;
}

.chart-wrap:hover .toplist-popover { display: block; }

.metrics { display: grid; gap: 4px; margin-top: 4px; }

.metric-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #b6d7ef;
  padding-top: 4px;
  border-top: 1px solid rgba(111, 244, 255, 0.12);
}

.metric-row strong { font-size: 12px; color: #6ff4ff; }
.metric-row strong.warn { color: #ffd35e; }

.load-error {
  position: absolute;
  bottom: 4px;
  right: 8px;
  margin: 0;
  font-size: 11px;
  color: #ffb7c3;
}
</style>
