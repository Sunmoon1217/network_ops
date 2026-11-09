<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { stylevar } from '@/ui/theme/dashboard_stylevar.ts'
import ZabbixAPI from '@/api/zabbix_api'
import MidCard_1 from '@/views/dashboard/components/MidCard-1.vue'
import MidCard_2 from '@/views/dashboard/components/MidCard-2.vue'
import MidCard_3 from '@/views/dashboard/components/MidCard-3.vue'
import MidCard_5 from '@/views/dashboard/components/MidCard-5.vue'
import ChartsCard_1 from '@/views/dashboard/components/ChartsCard-1.vue'
import ChartsCard_2 from '@/views/dashboard/components/ChartsCard-2.vue'
import { getdashboard } from '@/api/dashboard_api'
import { useInterval } from '@/utils/timer'

const StyleVar = stylevar

const DESIGN_WIDTH = 1920
const DESIGN_HEIGHT = 1080
const dashboardScale = ref(1)
const dashboardShellStyle = computed(() => ({
  ...StyleVar,
  '--screen-scale': dashboardScale.value.toString(),
}))

const zabbixApi = shallowRef<ZabbixAPI | null>(null)

type SummaryCard = {
  label: string
  value: string
  detail: string
  status: 'ok' | 'accent' | 'warn' | 'danger'
}

const summaryCards = ref<SummaryCard[]>([
  { label: '设备总量', value: '未采集', detail: 'IDC数据中心主机数', status: 'ok' },
  { label: '互联网链路健康度', value: '未采集', detail: '使用率超85% 未采集', status: 'accent' },
  { label: '巡检完成率', value: '未采集', detail: '今日已巡检 未采集', status: 'warn' },
  { label: '自动化工单', value: '未采集', detail: '成功率 未采集', status: 'ok' },
])

const updateDashboardScale = () => {
  const widthScale = window.innerWidth / DESIGN_WIDTH
  const heightScale = window.innerHeight / DESIGN_HEIGHT
  dashboardScale.value = Math.min(widthScale, heightScale)
}

const headerLeft = ['监控范围：网络设备 / 专线 / 机房']
const headerRight = ['刷新频率: 5 分钟']

const setSummaryCard = (label: SummaryCard['label'], patch: Partial<SummaryCard>) => {
  const card = summaryCards.value.find((item) => item.label === label)
  if (!card) return
  Object.assign(card, patch)
}

const notCollectedValue = '未采集'
const notCollectedDetail = '数据库未 更新/采集 数据'

const getSummaryValueClass = (card: SummaryCard) => {
  if (card.label !== '互联网链路健康度') return card.status

  if (card.value === notCollectedValue) return card.status

  const healthValue = Number.parseFloat(card.value)
  if (Number.isNaN(healthValue)) return card.status
  if (healthValue >= 99) return 'ok'
  if (healthValue >= 95) return 'accent'
  if (healthValue >= 90) return 'warn'
  return 'danger'
}

const fetch_device = async () => {
  const resp = await getdashboard('statusbar', 'devicecount')
  const data = resp.filter((item) => item.name === 'count')?.[0]?.list_value?.[0]
  if (!data) return
  setSummaryCard('设备总量', {
    value: `${Number(data?.count)}`,
    detail: `IDC数据中心监控中的主机数`,
  })
}
const fetch_link = async () => {
  const resp = await getdashboard('statusbar', 'linkhealthy')
  const data = resp.filter((item) => item.name === 'healthy')?.[0]?.list_value?.[0]
  if (!data) return
  setSummaryCard('互联网链路健康度', {
    value: `${Number(data?.healthy)}%`,
    detail: `使用率超85% ${data?.count} 次`,
  })
}
const fetch_inspection = async () => {
  const inspection = await getdashboard('statusbar', 'inspection')
  const success = inspection.filter((item) => item.name === 'success')
  const failed = inspection.filter((item) => item.name === 'warning')
  if (success.length === 0) {
    setSummaryCard('巡检完成率', { value: notCollectedValue, detail: notCollectedDetail })
  }
  setSummaryCard('巡检完成率', {
    value: String(success[0]?.value),
    detail: `今日已巡检 异常项: ${failed[0]?.value}`,
  })
}
const fetch_itsmtask = async () => {
  const resp = await getdashboard('statusbar', 'itsmtask')
  const data = resp.filter((item) => item.name === 'count')?.[0]?.list_value?.[0]
  if (!data) return
  setSummaryCard('自动化工单', {
    value: `${data.count}`,
    detail: `成功率: ${data.success}`,
  })
}

const fetch_date = async () => {
  fetch_device()
  fetch_link()
  fetch_inspection()
  fetch_itsmtask()
}

const { start } = useInterval(fetch_date, 3600 * 1000, true)

onMounted(() => {
  start()
  updateDashboardScale()
  window.addEventListener('resize', updateDashboardScale)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateDashboardScale)
  zabbixApi.value?.logout()
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
            <span v-for="item in headerRight" :key="item" class="header-meta">{{ item }}</span>
          </div>
        </header>

        <section class="status-bar panel-shell">
          <article v-for="card in summaryCards" :key="card.label" class="status-card">
            <p class="status-label">{{ card.label }}</p>
            <p class="status-value" :class="getSummaryValueClass(card)">{{ card.value }}</p>
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
              <MidCard_1 />
            </div>
          </section>

          <section class="panel-shell panel inspection">
            <div class="panel-title">
              <h2>每日巡检</h2>
              <span class="tag">健康检查</span>
            </div>
            <div class="panel-body">
              <MidCard_2 />
            </div>
          </section>

          <section class="panel-shell panel slb">
            <div class="panel-title">
              <h2>云平台 SLB 概览</h2>
              <span class="tag">实例/监听/节点</span>
            </div>
            <div class="panel-body">
              <MidCard_3 />
            </div>
          </section>

          <section class="panel-shell panel links">
            <div class="panel-title">
              <h2>重要链路概览</h2>
              <span class="tag">实时使用率</span>
            </div>
            <div class="panel-body">
              <ChartsCard_1 />
            </div>
          </section>

          <section class="panel-shell panel cabinets">
            <div class="panel-title">
              <h2>机柜使用情况</h2>
              <span class="tag">资源利用率</span>
            </div>
            <div class="panel-body">
              <MidCard_5 />
            </div>
          </section>

          <section class="panel-shell panel tickets">
            <div class="panel-title">
              <h2>自动化工单</h2>
              <span class="tag">执行明细</span>
            </div>
            <div class="panel-body">
              <ChartsCard_2 />
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
