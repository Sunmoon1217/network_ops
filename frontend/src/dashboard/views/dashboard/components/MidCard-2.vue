<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getdashboard } from '@/api/dashboard_api'
import { useInterval } from '@/utils/timer'

const online = ref(100)
const ulit = ref(0)
const count = ref(0)
const fetchData = async () => {
  const resopnse1 = await getdashboard('inspection', 'device')
  const resopnse2 = await getdashboard('inspection', 'link')
  const resopnse3 = await getdashboard('inspection', 'wdm')
  online.value = Number(resopnse1.filter((item) => item.name === 'online')[0]?.value)
  ulit.value = Number(resopnse2.filter((item) => item.name === 'online')[0]?.value)
  count.value = Number(resopnse3.filter((item) => item.name === 'online')[0]?.value)
}

const inspectionItems = computed(() => [
  {
    title: '设备信息',
    status: online.value == 100 ? '通过' : '关注',
    summary: `设备在线率 ${online.value}%，关键设备资源使用平稳`,
    extra: '完成率 100%',
    statusClass: 'ok',
  },
  {
    title: '三方专线',
    status: ulit.value < 80 ? '通过' : '关注',
    summary: '跨运营商链路无中断，核心时段带宽余量充足',
    extra: `平均利用率 ${ulit.value}%`,
    statusClass: 'ok',
  },
  {
    title: '波分裸光纤',
    status: count.value == 0 ? '通过' : '关注',
    summary: `${count.value} 条链路出现短时抖动，已安排持续观察`,
    extra: '',
    statusClass: 'warn',
  },
])

const { start } = useInterval(fetchData, 300 * 1000, true)

onMounted(() => {
  start()
})
</script>
<template>
  <div class="container">
    <div class="summary">
      <h4>巡检结果概览</h4>
      <p>今日巡检任务已完成 3/3, 建议持续关注波分链路波动</p>
    </div>
    <div class="items">
      <article class="item-card" v-for="item in inspectionItems" :key="item.title">
        <div class="item-head">
          <h5>{{ item.title }}</h5>
          <div class="status-badge" :class="item.statusClass">{{ item.status }}</div>
        </div>
        <p class="item-summary">{{ item.summary }}</p>
        <div class="item-extra">{{ item.extra }}</div>
      </article>
    </div>
  </div>
</template>
<style lang="css" scoped>
.container {
  height: 100%;
  display: grid;
  grid-template-rows: auto 1fr;
  gap: 8px;
}

.summary {
  border: 1px solid rgba(111, 244, 255, 0.16);
  border-radius: 12px;
  padding: 8px 10px;
  background: rgba(255, 255, 255, 0.03);
}

.summary h4 {
  margin: 0;
  font-size: 14px;
  color: #eaf6ff;
}

.summary p {
  margin: 6px 0 0;
  font-size: 12px;
  color: #b6d7ef;
}

.items {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  min-height: 0;
}

.item-card {
  border: 1px solid rgba(111, 244, 255, 0.16);
  border-radius: 12px;
  padding: 10px;
  display: grid;
  grid-template-rows: auto 1fr auto;
  gap: 8px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.045), rgba(255, 255, 255, 0.02));
}

.item-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.item-head h5 {
  margin: 0;
  font-size: 13px;
  color: #ecf7ff;
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
  border-color: rgba(255, 211, 94, 0.45);
  background: rgba(255, 211, 94, 0.12);
}

.item-summary {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: #cfe8ff;
}

.item-extra {
  font-size: 12px;
  color: #8ed0ff;
  padding-top: 6px;
  border-top: 1px solid rgba(111, 244, 255, 0.12);
}
</style>
