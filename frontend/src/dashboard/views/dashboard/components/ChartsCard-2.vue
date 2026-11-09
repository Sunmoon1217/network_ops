<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getdashboard } from '@/api/dashboard_api'
import { useInterval } from '@/utils/timer'
import type { DataTableProps, GlobalThemeOverrides } from 'naive-ui'

interface TicketItem {
  case_no: string
  title: string
  shenqing: string
  zhixing: string
  shijian: string
  status: '成功' | '失败' | '运行中' | null
}
const ticketList = ref<TicketItem[]>([])

const fetchData = async () => {
  try {
    const resp = await getdashboard('itsmtask', 'case')
    console.log('采集工单：', resp)
    ticketList.value = resp.map<TicketItem>((item) => {
      return {
        case_no: item.name,
        title: item.list_value[0].title,
        shenqing: item.list_value[0].shenqing,
        zhixing: item.list_value[0].zhixing ?? '',
        shijian: item.list_value[0].shijian ?? '',
        status: item.list_value[0].status ?? null,
      }
    })
  } catch {
    console.log('采集工单失败：')
    ticketList.value = []
  }
}

const colume = [
  { title: '标题', key: 'title', width: 100 },
  { title: '申请人', key: 'shenqing', width: 40 },
]

type DataTableOverrides = NonNullable<DataTableProps['themeOverrides']>
const datatableoverride: DataTableOverrides = {
  tdColor: '',
  tdTextColor: '',
  tdColorHover: 'transparent',
  thColor: '',
  thTextColor: '',
  thColorHover: 'transparent',
  borderColor: 'rgba(80, 244, 255, 0.16)',
  borderRadius: '12px',
}

const successCount = computed(
  () => ticketList.value.filter((item) => item.status === '成功').length,
)
const failedCount = computed(() => ticketList.value.filter((item) => item.status === '失败').length)
const runningCount = computed(
  () => ticketList.value.filter((item) => item.status === '运行中').length,
)
const successRate = computed(() =>
  ((successCount.value / ticketList.value.length) * 100).toFixed(1),
)

const { start } = useInterval(fetchData, 3600 * 1000, true)

onMounted(() => {
  start()
})
</script>

<template>
  <div class="container">
    <section class="overview">
      <article class="kpi-card">
        <p>今日工单总量</p>
        <strong>{{ ticketList.length }}</strong>
      </article>
      <!-- <article class="kpi-card success">
        <p>执行成功</p>
        <strong>{{ successCount }}</strong>
      </article>
      <article class="kpi-card running">
        <p>运行中</p>
        <strong>{{ runningCount }}</strong>
      </article>
      <article class="kpi-card danger">
        <p>执行失败</p>
        <strong>{{ failedCount }}</strong>
      </article>
      <article class="kpi-card">
        <p>成功率</p>
        <strong>{{ successRate }}%</strong>
      </article> -->
    </section>
    <n-data-table
      size="small"
      :columns="colume"
      :data="ticketList"
      :max-height="350"
      :theme-overrides="datatableoverride"
    />
  </div>
</template>

<style lang="css" scoped>
.container {
  height: 100%;
  width: 100%;
  overflow: hidden;
  display: grid;
  grid-template-rows: auto 1fr;
  gap: 8px;
}

.overview {
  display: grid;
  grid-template-columns: repeat(1, minmax(0, 1fr));
  gap: 8px;
}

.kpi-card {
  border: 1px solid rgba(111, 244, 255, 0.16);
  border-radius: 12px;
  padding: 8px 10px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.045), rgba(255, 255, 255, 0.02));
}

.kpi-card p {
  margin: 0;
  font-size: 12px;
  color: #a8cce6;
}

.kpi-card strong {
  margin-top: 4px;
  display: block;
  font-size: 20px;
  color: #6ff4ff;
  line-height: 1;
}

.kpi-card.success strong {
  color: #3dde9f;
}

.kpi-card.running strong {
  color: #ffd35e;
}

.kpi-card.danger strong {
  color: #ff6c84;
}

.table-wrap {
  border: 1px solid rgba(111, 244, 255, 0.14);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.02);
  overflow: hidden;
  min-height: 0;
  display: grid;
  grid-template-rows: auto 1fr;
}

.table-head,
.table-row {
  display: grid;
  grid-template-columns: 2.1fr 1fr 0.8fr 0.8fr 0.8fr;
  gap: 8px;
  align-items: center;
}

.table-head {
  padding: 8px 10px;
  font-size: 12px;
  color: #8eb8d8;
  border-bottom: 1px solid rgba(111, 244, 255, 0.14);
}

.table-body {
  overflow: auto;
}

.table-row {
  padding: 8px 10px;
  font-size: 12px;
  color: #d7ecfb;
  border-bottom: 1px solid rgba(111, 244, 255, 0.08);
}

.table-row:last-child {
  border-bottom: none;
}

.name {
  color: #ecf7ff;
}

.status {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 999px;
  font-style: normal;
  border: 1px solid transparent;
}

.status.成功 {
  color: #9af3cb;
  border-color: rgba(61, 222, 159, 0.4);
  background: rgba(61, 222, 159, 0.12);
}

.status.运行中 {
  color: #ffe49a;
  border-color: rgba(255, 211, 94, 0.45);
  background: rgba(255, 211, 94, 0.12);
}

.status.失败 {
  color: #ffb7c3;
  border-color: rgba(255, 108, 132, 0.45);
  background: rgba(255, 108, 132, 0.12);
}
</style>
