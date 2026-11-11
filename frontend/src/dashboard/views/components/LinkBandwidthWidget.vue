<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getLinkSeries } from '@/api/dashboard'
import type { ChartDataGroup, LinkPoint } from '@dashboard/types'
import LineCharts from '@dashboard/ui/LineCharts.vue'
import { useInterval } from '@dashboard/utils/timer'

const SCOPE_LABELS: Record<string, string> = {
  ipv4: 'IPv4 互联网链路',
  ipv6: 'IPv6 互联网链路',
  fwlink: '防火墙链路',
}
const SUBJECT_LABELS: Record<string, string> = {
  zjbgp: '中金BGP',
  jxqcu: '世纪互联联通',
  jxqct: '世纪互联电信',
  coreyw: '核心业务区',
  intyw: '互金业务区',
  mgtyw: '管理业务区',
  intdmz: '互联网DMZ',
}

const points = ref<LinkPoint[]>([])
const loadError = ref('')
const timeAxis = computed(() => points.value.map((point) => point.time))

const values = computed(() =>
  points.value.flatMap((point) =>
    Object.values(point.data).flatMap((scope) =>
      Object.values(scope).filter(
        (value): value is number => typeof value === 'number' && Number.isFinite(value),
      ),
    ),
  ),
)
const peak = computed(() => (values.value.length ? Math.max(...values.value) : null))
const subjectCount = computed(() => {
  const subjects = new Set<string>()
  points.value.forEach((point) =>
    Object.values(point.data).forEach((scope) => Object.keys(scope).forEach((key) => subjects.add(key))),
  )
  return subjects.size
})

// 后端返回的 EAV：{time, data: {scope: {subject: value}}}；系列按实际出现的 subject 动态生成。
const toGroups = (scopes: string[]): ChartDataGroup[] =>
  scopes.map((scope) => {
    const subjects = Array.from(
      new Set(points.value.flatMap((point) => Object.keys(point.data[scope] ?? {}))),
    )
    return {
      title: SCOPE_LABELS[scope] ?? scope,
      data: subjects.map((subject) => ({
        name: SUBJECT_LABELS[subject] ?? subject,
        value: points.value.map((point) => {
          const value = point.data[scope]?.[subject]
          // LineCharts 把 -1 转 null；后端未采到的样本 value 为 null，不能当成 0 画出来
          return typeof value === 'number' && Number.isFinite(value) ? value : -1
        }),
      })),
    }
  })

const extLinkData = computed(() => toGroups(['ipv4', 'ipv6']))
const fwLinkData = computed(() => toGroups(['fwlink']))

const fetchLinks = async () => {
  try {
    // 后端固定聚合最近 3 小时的 link_bandwidth 样本，无 since/until 参数，直接全量刷新
    const rows = await getLinkSeries()
    points.value = rows
      .filter((row) => row.name.startsWith('bandwidth-'))
      .map((row) => row.list_value?.[0] as LinkPoint | undefined)
      .filter((point): point is LinkPoint => Boolean(point?.data))
    loadError.value = ''
  } catch (error) {
    console.error('[dashboard] 链路数据获取失败:', error)
    loadError.value = '链路数据获取失败'
  }
}

const { start } = useInterval(fetchLinks, 5 * 60 * 1000, true)

onMounted(() => {
  start()
})
</script>

<template>
  <div class="container">
    <section class="items link-statistics">
      <div class="stats-title">
        <h4>链路运行总览</h4>
        <p>近 3 小时带宽峰值采样</p>
      </div>
      <div class="stats-total">
        <span>采样时间点</span>
        <strong>{{ points.length }}</strong>
      </div>
      <div class="stats-list">
        <article class="stats-card">
          <div class="stats-head"><span>监控链路</span><strong>{{ subjectCount }}</strong></div>
          <div class="stats-meta"><span>有效样本 {{ values.length }}</span><span>峰值 {{ peak === null ? '--' : peak.toFixed(1) + '%' }}</span></div>
        </article>
        <article class="stats-card">
          <div class="stats-head"><span>最新采样</span><strong>{{ timeAxis.length ? timeAxis[timeAxis.length - 1] : '--' }}</strong></div>
          <div class="stats-meta"><span>数据源 Zabbix</span><span>由后端采集落库</span></div>
        </article>
      </div>
      <p v-if="loadError" class="error">{{ loadError }}</p>
      <p v-else-if="!points.length" class="hint">近 3 小时暂无链路采样</p>
    </section>
    <div class="items linechart">
      <h4>互联网链路使用率</h4>
      <LineCharts v-if="points.length" :data="extLinkData" :xAxisData="timeAxis" />
      <div v-else class="chart-empty">暂无链路采样数据</div>
    </div>
    <div class="items linechart">
      <h4>防火墙链路使用率</h4>
      <LineCharts v-if="points.length" :data="fwLinkData" :xAxisData="timeAxis" />
      <div v-else class="chart-empty">暂无链路采样数据</div>
    </div>
  </div>
</template>

<style scoped>
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
  align-content: start;
}

.stats-title h4 { margin: 0; font-size: 15px; }
.stats-title p { margin: 4px 0 0; font-size: 12px; color: var(--muted); }

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

.stats-total strong { color: #6ff4ff; font-size: 26px; line-height: 1; }
.stats-list { display: grid; gap: 8px; align-content: start; }

.stats-card {
  border: 1px solid rgba(111, 244, 255, 0.14);
  border-radius: 12px;
  padding: 9px 10px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.02));
}

.stats-head { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; font-size: 13px; }
.stats-head strong { color: #34c8ff; font-size: 20px; line-height: 1; }
.stats-meta { margin-top: 6px; display: flex; justify-content: space-between; gap: 8px; font-size: 12px; color: #cfe8ff; }
.error { margin: 0; font-size: 11px; color: #ffb7c3; }
.hint { margin: 0; font-size: 11px; color: #88a9c8; }

.items { flex: 1; border: 1px solid var(--line); border-radius: 16px; min-height: 0; }
.linechart { display: flex; flex-direction: column; padding: 10px; gap: 8px; }
.linechart h4 { margin: 0; font-size: 14px; color: #d7efff; }
.chart-empty { flex: 1; display: grid; place-items: center; font-size: 12px; color: #88a9c8; }
</style>
