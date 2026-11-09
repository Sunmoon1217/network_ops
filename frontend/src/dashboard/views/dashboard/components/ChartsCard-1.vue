<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import ZabbixAPI from '@/api/zabbix_api'
import {
  buildRecentTimeAxis,
  calculateThresholdStats,
  createZabbixApiFromEnv,
  getHistoryByItemid,
  getItemsByGroupAndTag,
  getItemsByNameAndHostid,
  getRecentHistoryByItems,
} from '@/api/dashboard_zabbix'
import { processToPoint, mergeMax } from '@/utils/dataUtil'
import type { ChartData, ChartDataGroup } from '@/types'
import type { ZabbixHistoryPoint, ZabbixItem } from '@/types/zabbixapi'
import LineCharts from '@/ui/LineCharts.vue'
import { useMessage } from 'naive-ui'
import { getdashboard, getlinklatest } from '@/api/dashboard_api'
import { useInterval } from '@/utils/timer'
interface LinkSummaryItem {
  label: string
  total: number | string
  status: string
  risk: string
  trend: string
}

const LINK_SUMMARY_CONFIG = [
  { label: '互联网线路', groupName: '互联网边界', tagValue: 'internet' },
  { label: '三方专线', groupName: '外联边界', tagValue: 'ext' },
  { label: '广域网线路', groupName: '广域网', tagValue: 'wan' },
] as const
const notCollectedValue = '未采集'
const HISTORY_WINDOW_MINUTES = 180
const STEP_MINUTES = 3
const POLL_INTERVAL_MS = 5 * 60 * 1000
const timeAxisPoints = ref(buildRecentTimeAxis(HISTORY_WINDOW_MINUTES, STEP_MINUTES))
const timeAxis = ref<string[]>([])
const zjbgpv4 = ref<number[]>([])
const jxqctv4 = ref<number[]>([])
const jxqcuv4 = ref<number[]>([])
const zjbgpv6 = ref<number[]>([])
const jxqctv6 = ref<number[]>([])
const jxqcuv6 = ref<number[]>([])
const coreyw = ref<number[]>([])
const intyw = ref<number[]>([])
const mgtyw = ref<number[]>([])
const intdmz = ref<number[]>([])
let pollTimer: number | null = null

const extLinkData = ref<ChartDataGroup[]>([
  { title: 'IPv4', data: [] },
  { title: 'IPv6', data: [] },
])
const fwLinkData = ref<ChartDataGroup[]>([])
const grouptitle = ref('')
const linkSummary = ref<LinkSummaryItem[]>(
  LINK_SUMMARY_CONFIG.map((item) => ({
    label: item.label,
    total: notCollectedValue,
    status: `稳定 ${notCollectedValue}`,
    risk: `告警 ${notCollectedValue}`,
    trend: '近3小时',
  })),
)

const totalLinks = computed(() =>
  linkSummary.value.reduce(
    (sum, item) => sum + (typeof item.total === 'number' ? item.total : 0),
    0,
  ),
)

const refreshTimeAxis = () => {
  timeAxisPoints.value = buildRecentTimeAxis(HISTORY_WINDOW_MINUTES, STEP_MINUTES)
}

const buildSummaryItem = (
  label: string,
  total: number | string,
  stable: number | string,
  risk: number | string,
): LinkSummaryItem => ({
  label,
  total,
  status: `稳定 ${stable}`,
  risk: `告警 ${risk}`,
  trend: '近3小时',
})

const fetchLinkSummary = async () => {
  const response = await getdashboard('link', 'statistic')
  // console.log('获取链路统计信息:', response)
  const summary = LINK_SUMMARY_CONFIG.map((item) => {
    const value = response.filter((x) => x.name === item.tagValue)[0]?.list_value[0]
    // console.log('链路统计信息:', value)
    return buildSummaryItem(item.label, Number(value.count), value.stable, value.risk)
  })
  linkSummary.value = summary
}

const fetchLinks = async () => {
  const response = await getdashboard('link', 'linechart')
  const valuelist = response
    .filter((item) => item.name.includes('bandwidth'))
    .map((item) => item.list_value?.[0])
  // console.log('链路带宽信息:', datalist)
  const datalist = valuelist.map((item) => item?.data)
  timeAxis.value = valuelist.map((item) => item?.time)

  zjbgpv4.value = datalist.map((item) => Number(item?.ipv4.zjbgp))
  jxqctv4.value = datalist.map((item) => Number(item?.ipv4.jxqct))
  jxqcuv4.value = datalist.map((item) => Number(item?.ipv4.jxqcu))
  zjbgpv6.value = datalist.map((item) => Number(item?.ipv6.zjbgp))
  jxqctv6.value = datalist.map((item) => Number(item?.ipv6.jxqct))
  jxqcuv6.value = datalist.map((item) => Number(item?.ipv6.jxqcu))
  coreyw.value = datalist.map((item) => Number(item?.fwlink.coreyw))
  intyw.value = datalist.map((item) => Number(item?.fwlink.intyw))
  mgtyw.value = datalist.map((item) => Number(item?.fwlink.mgtyw))
  intdmz.value = datalist.map((item) => Number(item?.fwlink.intdmz))

  // console.log('timeAxis', timeAxis.value)
  // console.log('zjbgpv4', zjbgpv4.value)

  extLinkData.value = [
    {
      title: 'IPv4',
      data: [
        { name: '中金BGP', value: zjbgpv4.value },
        { name: '世纪互联联通', value: jxqcuv4.value },
        { name: '世纪互联电信', value: jxqctv4.value },
      ],
    },
    {
      title: 'IPv6',
      data: [
        { name: '中金BGP', value: zjbgpv6.value },
        { name: '世纪互联联通', value: jxqcuv6.value },
        { name: '世纪互联电信', value: jxqctv6.value },
      ],
    },
  ]
  fwLinkData.value = [
    {
      title: 'FWLink',
      data: [
        { name: '核心业务区', value: coreyw.value },
        { name: '互金业务区', value: intyw.value },
        { name: '管理业务区', value: mgtyw.value },
        { name: '互联网DMZ', value: intdmz.value },
      ],
    },
  ]
}

const fetchLinkUsage = async () => {
  try {
    refreshTimeAxis()
    await Promise.all([fetchLinkSummary(), fetchLinks()])
  } catch (error) {
    console.error('Failed to fetch link usage dashboard:', error)
    linkSummary.value = LINK_SUMMARY_CONFIG.map((item) =>
      buildSummaryItem(item.label, notCollectedValue, notCollectedValue, notCollectedValue),
    )
    extLinkData.value = [
      {
        title: 'IPv4',
        data: [
          { name: '中金BGP', value: Array(60).fill(0) },
          { name: '世纪互联联通', value: Array(60).fill(0) },
          { name: '世纪互联电信', value: Array(60).fill(0) },
        ],
      },
      {
        title: 'IPv6',
        data: [
          { name: '中金BGP', value: Array(60).fill(0) },
          { name: '世纪互联联通', value: Array(60).fill(0) },
          { name: '世纪互联电信', value: Array(60).fill(0) },
        ],
      },
    ]
    fwLinkData.value = [
      {
        title: 'FWLink',
        data: [
          { name: '核心业务区', value: Array(60).fill(0) },
          { name: '互金业务区', value: Array(60).fill(0) },
          { name: '管理业务区', value: Array(60).fill(0) },
          { name: '互联网DMZ', value: Array(60).fill(0) },
        ],
      },
    ]
  }
}

const update = async () => {
  const now = new Date()
  const minutes = now.getMinutes()
  const roundedMinutes = minutes - (minutes % 3)
  const roundedNow = new Date(now.getTime())
  roundedNow.setSeconds(0, 0) // 清除秒和毫秒
  roundedNow.setMinutes(roundedMinutes) // 对齐到最近的 stepMinutes 倍数

  const label = `${roundedNow.getHours().toString().padStart(2, '0')}:${roundedNow.getMinutes().toString().padStart(2, '0')}`

  if (!timeAxis.value.includes(label)) {
    const response = await getlinklatest(label)
    const data = response[0].list_value[0]
    if (!data.value) return
    timeAxis.value.shift()
    zjbgpv4.value.shift()
    jxqctv4.value.shift()
    jxqcuv4.value.shift()
    zjbgpv6.value.shift()
    jxqctv6.value.shift()
    jxqcuv6.value.shift()
    coreyw.value.shift()
    intyw.value.shift()
    mgtyw.value.shift()
    intdmz.value.shift()
    timeAxis.value.push(data.time)
    zjbgpv4.value.push(data.data.ipv4.zjbgp)
    jxqctv4.value.push(data.data.ipv4.jxqct)
    jxqcuv4.value.push(data.data.ipv4.jxqcu)
    zjbgpv6.value.push(data.data.ipv6.zjbgp)
    jxqctv6.value.push(data.data.ipv6.jxqct)
    jxqcuv6.value.push(data.data.ipv6.jxqcu)
    coreyw.value.push(data.data.fwlink.coreyw)
    intyw.value.push(data.data.fwlink.intyw)
    mgtyw.value.push(data.data.fwlink.mgtyw)
    intdmz.value.push(data.data.fwlink.intdmz)
  }
}

const { start } = useInterval(update, 3 * 60 * 1000, false)

const startPolling = () => {
  pollTimer = window.setInterval(() => {
    fetchLinkUsage()
  }, POLL_INTERVAL_MS)
}

onMounted(() => {
  fetchLinkUsage()
  start()
  startPolling()
})

onBeforeUnmount(() => {
  if (pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
})
</script>
<template>
  <div class="container">
    <section class="items link-statistics">
      <div class="stats-title">
        <h4>链路运行总览</h4>
        <p>重点关注稳定性与波动趋势</p>
      </div>
      <div class="stats-total">
        <span>监控链路总数</span>
        <strong>{{ totalLinks || notCollectedValue }}</strong>
      </div>
      <div class="stats-list">
        <article class="stats-card" v-for="item in linkSummary" :key="item.label">
          <div class="stats-head">
            <span>{{ item.label }}</span>
            <strong>{{ item.total }}</strong>
          </div>
          <div class="stats-meta">
            <span>{{ item.status }}</span>
            <span>{{ item.risk }}</span>
          </div>
          <div class="stats-trend">{{ item.trend }}</div>
        </article>
      </div>
    </section>
    <div class="items linechart">
      <h4>互联网链路使用率 {{ grouptitle }}</h4>
      <LineCharts :data="extLinkData" :xAxisData="timeAxis" v-model="grouptitle" />
    </div>
    <div class="items linechart">
      <h4>防火墙链路使用率</h4>
      <LineCharts :data="fwLinkData" :xAxisData="timeAxis" />
    </div>
  </div>
</template>
<style lang="css" scoped>
.container {
  height: 100%;
  display: grid;
  grid-template-rows: 1fr 1fr;
  grid-template-columns: 2fr 8fr;
  gap: 0.3rem;
  overflow: hidden;
}

.link-statistics {
  grid-row: span 2;
  padding: 10px;
  display: grid;
  gap: 8px;
  grid-template-rows: auto auto 1fr;
}

.stats-title h4 {
  margin: 0;
  font-size: 15px;
}

.stats-title p {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--muted);
}

.stats-total {
  border: 1px solid rgba(111, 244, 255, 0.14);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.03);
  padding: 8px 10px;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  color: #b8d5ec;
  font-size: 12px;
}

.stats-total strong {
  color: #6ff4ff;
  font-size: 26px;
  line-height: 1;
}

.stats-list {
  display: grid;
  gap: 8px;
}

.stats-card {
  border: 1px solid rgba(111, 244, 255, 0.14);
  border-radius: 12px;
  padding: 9px 10px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.02));
}

.stats-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 10px;
  font-size: 13px;
}

.stats-head strong {
  color: #34c8ff;
  font-size: 20px;
  line-height: 1;
}

.stats-meta {
  margin-top: 6px;
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  color: #cfe8ff;
}

.stats-trend {
  margin-top: 6px;
  font-size: 12px;
  color: #9fd7ff;
}

.items {
  flex: 1;
  border: 1px solid var(--line);
  border-radius: 16px;
  min-height: 0;
}

.linechart {
  display: flex;
  flex-direction: column;
  padding: 10px;
  gap: 8px;
}

.linechart h4 {
  margin: 0;
  font-size: 14px;
  color: #d7efff;
}
</style>
