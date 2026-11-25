<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getDashboard } from '@/api/dashboard'
import type { TicketItem } from '@dashboard/types'
import { useInterval } from '@dashboard/utils/timer'

const tickets = ref<TicketItem[]>([])
const loadError = ref('')

const successCount = computed(() => tickets.value.filter((item) => item.status === '成功').length)
const failedCount = computed(() => tickets.value.filter((item) => item.status === '失败').length)
const runningCount = computed(() => tickets.value.filter((item) => item.status === '运行中').length)
const successRate = computed(() =>
  tickets.value.length ? ((100 * successCount.value) / tickets.value.length).toFixed(1) : '0.0',
)

const fetchData = async () => {
  try {
    // write_dashboard 把每张工单物化成 itsmtask/case/<case_no>，list_value[0] 是外部原始字段
    const rows = await getDashboard({ panel: 'itsmtask', group: 'case' })
    tickets.value = rows.map((row) => {
      const raw = (row.list_value?.[0] ?? {}) as Partial<TicketItem>
      return {
        case_no: row.name,
        title: raw.title ?? row.name,
        shenqing: raw.shenqing ?? '',
        zhixing: raw.zhixing,
        shijian: raw.shijian,
        status: raw.status ?? null,
      }
    })
    loadError.value = ''
  } catch (error) {
    console.error('[dashboard] 工单数据获取失败:', error)
    loadError.value = '工单数据获取失败'
  }
}

const { start } = useInterval(fetchData, 5 * 60 * 1000, true)

onMounted(() => {
  start()
})
</script>

<template>
  <div class="container">
    <section class="overview">
      <article class="kpi-card"><p>工单总量</p><strong>{{ tickets.length }}</strong></article>
      <article class="kpi-card success"><p>执行成功</p><strong>{{ successCount }}</strong></article>
      <article class="kpi-card running"><p>运行中</p><strong>{{ runningCount }}</strong></article>
      <article class="kpi-card danger"><p>执行失败</p><strong>{{ failedCount }}</strong></article>
      <article class="kpi-card"><p>成功率</p><strong>{{ successRate }}%</strong></article>
    </section>
    <div class="table-wrap">
      <p v-if="loadError" class="error">{{ loadError }}</p>
      <p v-else-if="!tickets.length" class="empty">暂无工单数据</p>
      <table v-else>
        <thead>
          <tr><th>标题</th><th>工单号</th><th>申请人</th><th>状态</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in tickets" :key="item.case_no">
            <td :title="item.title">{{ item.title }}</td>
            <td>{{ item.case_no }}</td>
            <td>{{ item.shenqing || '--' }}</td>
            <td><span class="status" :class="item.status || 'unknown'">{{ item.status || '未采集' }}</span></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.container { height: 100%; width: 100%; overflow: hidden; display: grid; grid-template-rows: auto 1fr; gap: 8px; }

.overview { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 6px; }

.kpi-card {
  border: 1px solid rgba(111, 244, 255, 0.16);
  border-radius: 12px;
  padding: 8px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.045), rgba(255, 255, 255, 0.02));
}

.kpi-card p { margin: 0; font-size: 11px; color: #a8cce6; }
.kpi-card strong { margin-top: 4px; display: block; font-size: 18px; color: #6ff4ff; line-height: 1; }
.kpi-card.success strong { color: #3dde9f; }
.kpi-card.running strong { color: #ffd35e; }
.kpi-card.danger strong { color: #ff6c84; }

.table-wrap { min-height: 0; overflow: auto; font-size: 12px; color: #d7ecfb; }
.table-wrap::-webkit-scrollbar { width: 4px; }
.table-wrap table { width: 100%; border-collapse: collapse; }
.table-wrap th, .table-wrap td { padding: 6px 8px; text-align: left; border-bottom: 1px solid rgba(111, 244, 255, 0.1); }
.table-wrap th { color: #8eb8d8; font-weight: 500; }
.table-wrap td:first-child { max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.error, .empty { margin: 0; padding: 10px; color: #88a9c8; }
.error { color: #ffb7c3; }

.status { display: inline-block; padding: 1px 8px; border-radius: 999px; border: 1px solid transparent; font-style: normal; }
.status.成功 { color: #9af3cb; border-color: rgba(61, 222, 159, 0.4); background: rgba(61, 222, 159, 0.12); }
.status.运行中 { color: #ffe49a; border-color: rgba(255, 211, 94, 0.45); background: rgba(255, 211, 94, 0.12); }
.status.失败 { color: #ffb7c3; border-color: rgba(255, 108, 132, 0.45); background: rgba(255, 108, 132, 0.12); }
.status.unknown { color: #9fb6cc; border-color: rgba(159, 182, 204, 0.3); background: rgba(159, 182, 204, 0.1); }
</style>
