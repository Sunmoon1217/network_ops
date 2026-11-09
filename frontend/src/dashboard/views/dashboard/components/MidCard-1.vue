<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  buildTopListFromItems,
  getMaxValueFromItems,
  normalizePercent,
} from '@/api/dashboard_zabbix'
import GaugeCharts from '@/ui/GaugeCharts.vue'
import DeviceTopList from './DeviceTopList.vue'
import { getdashboard } from '@/api/dashboard_api'
import type { ZabbixItem } from '@/types'
import { isZabbixItem } from '@/utils/dataUtil'
import { useInterval } from '@/utils/timer'

interface GaugeDatum {
  name: string
  value: number
  itemStyle: { color: string }
  title: { offsetCenter: [string, string] }
  detail: { valueAnimation: boolean; offsetCenter: [string, string] }
}

interface DeviceTopItem {
  label: string
  value: number
}

interface DeviceCard {
  name: string
  groupName?: string
  status: string
  statusClass: 'ok' | 'warn'
  gaugeData: GaugeDatum[]
  metrics: Array<{ label: string; value: string; className: 'ok' | 'accent' | 'warn' }>
  top: {
    cpu: DeviceTopItem[]
    memory: DeviceTopItem[]
  }
}

const notCollectedValue = '未采集'

const CARD_CONFIG = [
  { name: '交换机', groupName: 'Type:交换机', group: 'switch' },
  { name: '路由器', groupName: 'Type:路由器', group: 'router' },
  { name: '防火墙', groupName: 'Type:防火墙', group: 'firewall' },
  { name: '负载均衡', groupName: 'Type:负载均衡', group: 'loadbalance' },
  { name: 'DNS', groupName: 'Type:DNS', group: 'dns' },
] as const

const createGaugeData = (cpu: number, memory: number): GaugeDatum[] => [
  {
    name: 'CPU',
    value: normalizePercent(cpu),
    itemStyle: { color: '#34c8ff' },
    title: { offsetCenter: ['0%', '-40%'] },
    detail: { valueAnimation: true, offsetCenter: ['0%', '-15%'] },
  },
  {
    name: '内存',
    value: normalizePercent(memory),
    itemStyle: { color: '#9f92ff' },
    title: { offsetCenter: ['0%', '15%'] },
    detail: { valueAnimation: true, offsetCenter: ['0%', '40%'] },
  },
]

const createDefaultCard = (name: string, groupName: string): DeviceCard => ({
  name,
  groupName,
  status: notCollectedValue,
  statusClass: 'warn',
  gaugeData: createGaugeData(0, 0),
  metrics: [
    { label: '在线设备', value: notCollectedValue, className: 'accent' },
    { label: '告警', value: notCollectedValue, className: 'warn' },
  ],
  top: {
    cpu: [],
    memory: [],
  },
})

const cards = ref<DeviceCard[]>(
  CARD_CONFIG.map((item) => createDefaultCard(item.name, item.groupName)),
)

const fetchCardData = async (name: string, group: string): Promise<DeviceCard> => {
  const response = await getdashboard('devicestatus', group)
  const rowcount = response.filter((item) => item.name == 'count')
  const rowperfprob = response.filter((item) => item.name == 'perfprob')
  const rowalert = response.filter((item) => item.name == 'problems')
  const cpumax = response.filter((item) => item.name == 'cpumax')
  const memmax = response.filter((item) => item.name == 'memmax')
  const rowcputop = response.filter((item) => item.name == 'cputop')
  const rowmemtop = response.filter((item) => item.name == 'memtop')

  let cpuItems: ZabbixItem[] = []
  rowcputop[0]?.list_value.forEach((item) => {
    if (isZabbixItem(item)) {
      cpuItems.push(item)
    }
  })
  let memoryItems: ZabbixItem[] = []
  rowmemtop[0]?.list_value.forEach((item) => {
    if (isZabbixItem(item)) {
      memoryItems.push(item)
    }
  })

  const hostCountResult = Number(rowcount[0]?.value ?? 0)
  const pfalertCount = Number(rowperfprob[0]?.value ?? 0)
  const problemCount = Number(rowalert[0]?.list_value.length ?? 0)
  const hasProblems = !Number.isNaN(problemCount) && problemCount > 0

  return {
    name,
    status: hasProblems ? '存在告警' : '运行正常',
    statusClass: hasProblems ? 'warn' : 'ok',
    gaugeData: createGaugeData(Number(cpumax[0]?.value), Number(memmax[0]?.value)),
    metrics: [
      {
        label: '在线设备',
        value: String(hostCountResult) || notCollectedValue,
        className: 'accent',
      },
      {
        label: '告警',
        value: `${pfalertCount.toString() ?? notCollectedValue}/${problemCount.toString() ?? notCollectedValue}`,
        className: hasProblems ? 'warn' : 'ok',
      },
    ],
    top: {
      cpu: rowcputop[0]!.list_value,
      memory: rowmemtop[0]!.list_value,
    },
  }
}

const fetchCards = async () => {
  try {
    cards.value = await Promise.all(CARD_CONFIG.map((item) => fetchCardData(item.name, item.group)))
  } catch (error) {
    console.error('Failed to fetch device overview cards:', error)
    cards.value = CARD_CONFIG.map((item) => createDefaultCard(item.name, item.groupName))
  }
}

const { start } = useInterval(fetchCards, 5 * 60 * 1000, true)

onMounted(() => {
  start()
})
</script>
<template>
  <div class="container">
    <div class="items" v-for="card in cards" :key="card.name">
      <div class="item-head">
        <h4>{{ card.name }}</h4>
        <span class="status-badge" :class="card.statusClass">{{ card.status }}</span>
      </div>
      <n-tooltip placement="bottom-end" raw>
        <template #trigger>
          <div class="chart-wrap">
            <GaugeCharts :data="card.gaugeData" />
            <div class="gauge-legend">
              <span class="legend low">低负载</span>
              <span class="legend medium">中负载</span>
              <span class="legend high">高负载</span>
            </div>
          </div>
        </template>
        <DeviceTopList :data="card.top" />
      </n-tooltip>
      <div class="metrics">
        <div class="metric-row" v-for="metric in card.metrics" :key="metric.label">
          <span>{{ metric.label }}</span>
          <strong :class="metric.className">{{ metric.value }}</strong>
        </div>
      </div>
    </div>
  </div>
</template>
<style lang="css" scoped>
.container {
  height: 100%;
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0.5em;
}

.items {
  border: 1px solid var(--line);
  border-radius: 16px;
  display: grid;
  grid-template-rows: auto minmax(132px, 1fr) auto;
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

.status-badge.ok {
  color: #9af3cb;
  border-color: rgba(61, 222, 159, 0.4);
  background: rgba(61, 222, 159, 0.12);
}

.status-badge.warn {
  color: #ffe49a;
  border-color: rgba(255, 211, 94, 0.4);
  background: rgba(255, 211, 94, 0.12);
}

.chart-wrap {
  height: 100%;
  min-height: 0;
  padding: 2px 0 0;
  display: grid;
  grid-template-rows: 1fr auto;
}

.gauge-legend {
  display: flex;
  justify-content: center;
  gap: 8px;
  margin-top: -6px;
  margin-bottom: 0;
}

.legend {
  position: relative;
  padding-left: 10px;
  font-size: 9px;
  color: #9fbfd8;
}

.legend::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  transform: translateY(-50%);
}

.legend.low::before {
  background: #3dde9f;
}

.legend.medium::before {
  background: #ffd35e;
}

.legend.high::before {
  background: #ff6c84;
}

.metrics {
  display: grid;
  gap: 6px;
  margin-top: 4px;
}

.metric-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: #b6d7ef;
  padding-top: 6px;
  border-top: 1px solid rgba(111, 244, 255, 0.12);
}

.metric-row strong {
  font-size: 14px;
}

.accent {
  color: #6ff4ff;
}

.ok {
  color: #3dde9f;
}

.warn {
  color: #ffd35e;
}
</style>
