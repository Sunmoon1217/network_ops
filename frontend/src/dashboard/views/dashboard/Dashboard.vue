<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { stylevar } from '@dashboard/ui/theme/dashboard_stylevar'
import { getDashboard, getLinkSeries } from '@/api/dashboard'
import type { DashboardData, InspectItem, LinkPoint } from '@dashboard/types'
import { useInterval } from '@dashboard/utils/timer'
import DeviceStatusWidget from './components/DeviceStatusWidget.vue'
import InspectionWidget from './components/InspectionWidget.vue'
import SlbOverviewWidget from './components/SlbOverviewWidget.vue'
import LinkBandwidthWidget from './components/LinkBandwidthWidget.vue'
import CabinetUsageWidget from './components/CabinetUsageWidget.vue'
import AutomationTicketWidget from './components/AutomationTicketWidget.vue'

const StyleVar = stylevar

const DESIGN_WIDTH = 1920
const DESIGN_HEIGHT = 1080
const REFRESH_MS = 5 * 60 * 1000
const EMPTY = '暂无数据'
const dashboardScale = ref(1)
const dashboardShellStyle = computed(() => ({
  ...StyleVar,
  '--screen-scale': dashboardScale.value.toString(),
}))

type SummaryCard = {
  label: string
  value: string
  detail: string
  status: 'ok' | 'accent' | 'warn' | 'danger'
}

const summaryCards = ref<SummaryCard[]>([
  { label: '监控设备总量', value: EMPTY, detail: 'Zabbix 主机组设备数', status: 'ok' },
  { label: '链路峰值使用率', value: EMPTY, detail: '近 3 小时链路采样', status: 'accent' },
  { label: '今日巡检设备', value: EMPTY, detail: '巡检采集结果', status: 'ok' },
  { label: '自动化工单', value: EMPTY, detail: '成功率未采集', status: 'ok' },
])
const updatedAt = ref('--:--:--')
const loadError = ref('')

const updateDashboardScale = () => {
  const widthScale = window.innerWidth / DESIGN_WIDTH
  const heightScale = window.innerHeight / DESIGN_HEIGHT
  dashboardScale.value = Math.min(widthScale, heightScale)
}

const headerLeft = ['监控范围：网络设备 / 专线 / 机房']

const setCard = (label: string, patch: Partial<SummaryCard>) => {
  const card = summaryCards.value.find((item) => item.label === label)
  if (card) Object.assign(card, patch)
}

const toNumber = (value: unknown): number | null => {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

const metricRow = (rows: DashboardData[], panel: string, group: string, name: string) =>
  rows.find((item) => item.panel === panel && item.group === group && item.name === name)

const fetchSummary = async () => {
  try {
    // 只取状态栏与巡检两个 panel，避免把工单明细、设备状态全表一起拉回来
    const [statusbar, inspectionRows, series] = await Promise.all([
      getDashboard({ panel: 'statusbar' }),
      getDashboard({ panel: 'inspection' }),
      getLinkSeries(),
    ])

    const deviceCount = toNumber(
      metricRow(statusbar, 'statusbar', 'devicecount', 'count')?.list_value?.[0]?.count,
    )
    setCard('监控设备总量', {
      value: deviceCount === null ? EMPTY : String(deviceCount),
      detail: 'Zabbix 主机组设备数',
    })

    const points = series
      .filter((item) => item.name.startsWith('bandwidth-'))
      .map((item) => item.list_value?.[0] as LinkPoint | undefined)
      .filter((point): point is LinkPoint => Boolean(point?.data))
    const latest = points.length ? points[points.length - 1] : null
    const values = Object.values(latest?.data ?? {}).flatMap((scope) =>
      Object.values(scope).filter(
        (value): value is number => typeof value === 'number' && Number.isFinite(value),
      ),
    )
    const peak = values.length ? Math.max(...values) : null
    setCard('链路峰值使用率', {
      value: peak === null ? EMPTY : `${peak.toFixed(1)}%`,
      detail: points.length
        ? `近 3 小时 ${points.length} 个采样点 · ${values.length} 条链路`
        : '近 3 小时暂无链路采样',
      status: peak === null ? 'accent' : peak >= 85 ? 'danger' : peak >= 70 ? 'warn' : 'ok',
    })

    const inspect = (metricRow(inspectionRows, 'inspection', 'device', 'list')?.list_value ??
      []) as InspectItem[]
    const cpuMax = inspect.length
      ? Math.max(...inspect.map((item) => toNumber(item.cpu_max) ?? 0))
      : null
    const memMax = inspect.length
      ? Math.max(...inspect.map((item) => toNumber(item.memory_max) ?? 0))
      : null
    setCard('今日巡检设备', {
      value: inspect.length ? String(inspect.length) : EMPTY,
      detail: cpuMax === null ? '巡检采集未写入' : `CPU 峰值 ${cpuMax}% · 内存峰值 ${memMax}%`,
    })

    const itsm = metricRow(statusbar, 'statusbar', 'itsmtask', 'count')?.list_value?.[0]
    const ticketCount = toNumber(itsm?.count)
    const success = toNumber(itsm?.success)
    setCard('自动化工单', {
      value: ticketCount === null ? EMPTY : String(ticketCount),
      detail: success === null ? '成功率未采集' : `成功率 ${success}%`,
    })

    updatedAt.value = new Date().toLocaleTimeString()
    loadError.value = ''
  } catch (error) {
    console.error('[dashboard] 概览获取失败:', error)
    loadError.value = '数据获取失败：/api/dashboard/ 不可达或未登录'
  }
}

const { start } = useInterval(fetchSummary, REFRESH_MS, true)

onMounted(() => {
  start()
  updateDashboardScale()
  window.addEventListener('resize', updateDashboardScale)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateDashboardScale)
})
</script>

<template>
  <div class="dashboard-shell" :style="dashboardShellStyle">
    <div class="dashboard-frame">
      <div class="dashboard">
        <header class="header panel-shell">
          <div class="header-side">
            <span v-for="item in headerLeft" :key="item" class="header-meta">{{ item }}</span>
          </div>
          <div class="title">
            <h1>网络运维监控大屏</h1>
            <p>设备状态、链路质量、巡检任务、自动化工单统一可视化</p>
          </div>
          <div class="header-side right">
            <span v-if="loadError" class="header-meta error">{{ loadError }}</span>
            <span class="header-meta">刷新于 {{ updatedAt }} · 每 5 分钟</span>
          </div>
        </header>

        <section class="status-bar panel-shell">
          <article v-for="card in summaryCards" :key="card.label" class="status-card">
            <p class="status-label">{{ card.label }}</p>
            <p class="status-value" :class="card.status">{{ card.value }}</p>
            <p class="status-detail">{{ card.detail }}</p>
          </article>
        </section>

        <main class="content-grid">
          <section class="panel-shell panel overview">
            <div class="panel-title">
              <h2>设备运行状态</h2>
              <span class="tag">CPU / 内存 / 硬件告警</span>
            </div>
            <div class="panel-body">
              <DeviceStatusWidget />
            </div>
          </section>

          <section class="panel-shell panel inspection">
            <div class="panel-title">
              <h2>每日巡检</h2>
              <span class="tag">健康检查</span>
            </div>
            <div class="panel-body">
              <InspectionWidget />
            </div>
          </section>

          <section class="panel-shell panel slb">
            <div class="panel-title">
              <h2>云平台 SLB 概览</h2>
              <span class="tag">实例 / 监听</span>
            </div>
            <div class="panel-body">
              <SlbOverviewWidget />
            </div>
          </section>

          <section class="panel-shell panel links">
            <div class="panel-title">
              <h2>重要链路概览</h2>
              <span class="tag">近 3 小时峰值</span>
            </div>
            <div class="panel-body">
              <LinkBandwidthWidget />
            </div>
          </section>

          <section class="panel-shell panel cabinets">
            <div class="panel-title">
              <h2>机柜使用情况</h2>
              <span class="tag">资产库 U 位</span>
            </div>
            <div class="panel-body">
              <CabinetUsageWidget />
            </div>
          </section>

          <section class="panel-shell panel tickets">
            <div class="panel-title">
              <h2>自动化工单</h2>
              <span class="tag">执行明细</span>
            </div>
            <div class="panel-body">
              <AutomationTicketWidget />
            </div>
          </section>
        </main>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dashboard-shell {
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    linear-gradient(180deg, rgba(15, 96, 155, 0.12), transparent 28%),
    radial-gradient(circle at top, rgba(33, 171, 255, 0.12), transparent 28%),
    linear-gradient(180deg, var(--bg-2) 0%, var(--bg-1) 100%);
}

.dashboard-frame {
  width: 1920px;
  height: 1080px;
  transform: scale(var(--screen-scale, 1));
  transform-origin: center center;
}

.dashboard {
  width: 1928px;
  height: 1092px;
  padding: 14px;
  overflow: hidden;
  display: grid;
  grid-template-rows: 86px 120px minmax(560px, 1fr);
  gap: 12px;
  font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  color: var(--text);
}

.panel-shell {
  border: 1px solid var(--line);
  border-radius: 12px;
  background: linear-gradient(180deg, var(--panel), var(--panel-soft));
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.02),
    0 12px 28px rgba(0, 0, 0, 0.24),
    0 0 30px rgba(36, 150, 255, 0.06);
}

.header {
  padding: 0 20px;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
}

.header-side {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.header-side.right {
  justify-content: flex-end;
  align-items: center;
}

.header-meta {
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(52, 200, 255, 0.2);
  background: rgba(52, 200, 255, 0.08);
  color: var(--muted);
  font-size: 12px;
}

.header-meta.error {
  border-color: rgba(255, 108, 132, 0.4);
  background: rgba(255, 108, 132, 0.1);
  color: var(--red);
}

.screen-btn {
  --el-button-bg-color: rgba(52, 200, 255, 0.12);
  --el-button-border-color: rgba(52, 200, 255, 0.22);
  --el-button-hover-bg-color: rgba(52, 200, 255, 0.2);
  --el-button-hover-border-color: rgba(111, 244, 255, 0.44);
  --el-button-text-color: #d9f5ff;
  --el-button-hover-text-color: #ecf9ff;
  border-radius: 999px;
  padding: 7px 14px;
}

.title {
  text-align: center;
}

.title h1 {
  margin: 0;
  font-size: 30px;
  letter-spacing: 2px;
}

.title p {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--muted);
}

.status-bar {
  padding: 8px 12px;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.status-card {
  border: 1px solid rgba(130, 191, 239, 0.12);
  border-radius: 12px;
  padding: 12px 14px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.045), rgba(255, 255, 255, 0.02));
}

.status-label {
  margin: 0;
  font-size: 12px;
  color: var(--muted);
}

.status-value {
  margin: 8px 0 6px;
  font-size: 32px;
  line-height: 1;
  font-weight: 700;
}

.status-detail {
  margin: 0;
  font-size: 12px;
  color: #cfe8ff;
}

.ok {
  color: var(--green);
}

.accent {
  color: var(--blue);
}

.warn {
  color: var(--yellow);
}

.danger {
  color: var(--red);
}

.content-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(4, 1fr);
  grid-template-rows: 1.2fr 1fr 1fr;
  grid-template-areas:
    'overview overview inspection slb'
    'links links cabinets tickets'
    'links links cabinets tickets';
}

.panel {
  min-width: 0;
  min-height: 0;
  padding: 8px;
  display: flex;
  flex-direction: column;
}

.overview {
  grid-area: overview;
}

.inspection {
  grid-area: inspection;
}

.slb {
  grid-area: slb;
}

.links {
  grid-area: links;
}

.interfaces {
  grid-area: interfaces;
}

.cabinets {
  grid-area: cabinets;
}

.tickets {
  grid-area: tickets;
}

.panel-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.panel-title h2 {
  margin: 0;
  font-size: 16px;
}

.tag {
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 11px;
  color: #ddf5ff;
  background: rgba(52, 200, 255, 0.1);
  border: 1px solid rgba(52, 200, 255, 0.2);
}

.panel-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
</style>
