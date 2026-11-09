<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useInterval } from '@/utils/timer'
import { getdashboard } from '@/api/dashboard_api'

const instance = ref(200)
const slb_trend = ref(0)
instance.value = Math.floor(Math.random() * 200) + 300
const monitor = ref(300)
const monitor_trend = ref(0)
monitor.value = Math.floor((Math.random() + 1) * instance.value)
const node = ref(500)
const node_trend = ref(0)
node.value = Math.floor((Math.random() + 1) * monitor.value)

const fetchData = async () => {
  const resp = await getdashboard('slb', 'slb')
  const data = resp.filter((item) => item.name === 'slb')?.[0].list_value?.[0]
  if (!data) return

  const new_instance = Number(data.instance)
  const new_monitor = Number(data.listener)

  slb_trend.value = new_instance - instance.value
  instance.value = new_instance
  monitor_trend.value = new_monitor - instance.value
  monitor.value = new_monitor
}

const slbSummary = computed(() => [
  {
    label: 'SLB 实例总数',
    value: instance,
    unit: '个',
    detail: '云-生产环境负载均衡',
    trend: `${slb_trend.value}%`,
    trendClass: slb_trend.value >= 0 ? 'up' : 'down',
  },
  {
    label: 'SLB 监听总数',
    value: monitor,
    unit: '个',
    detail: 'TCP/HTTP/HTTPS 监听项',
    trend: `${monitor_trend.value}%`,
    trendClass: slb_trend.value >= 0 ? 'up' : 'down',
  },
  // {
  //   label: '后端节点总数',
  //   value: node,
  //   unit: '个',
  //   detail: '已接入后端服务节点',
  //   trend: `${node_trend.value}%`,
  //   trendClass: slb_trend.value >= 0 ? 'up' : 'down',
  // },
])

const { start } = useInterval(fetchData, 3600 * 1000, true)

onMounted(() => {
  start()
})
</script>
<template>
  <div class="cloud-slb">
    <div class="slb-header">
      <h4>云平台负载均衡状态</h4>
      <span class="health">总体健康</span>
    </div>
    <div class="slb-grid">
      <article class="slb-card" v-for="item in slbSummary" :key="item.label">
        <p class="label">{{ item.label }}</p>
        <p class="value">
          {{ item.value }} <small>{{ item.unit }}</small>
        </p>
        <p class="detail">{{ item.detail }}</p>
        <p class="trend" :class="item.trendClass">较昨日 {{ item.trend }}</p>
      </article>
    </div>
  </div>
</template>

<style lang="css" scoped>
.cloud-slb {
  height: 100%;
  box-sizing: border-box;
  display: grid;
  grid-template-rows: auto 1fr;
  gap: 10px;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: linear-gradient(180deg, var(--panel), var(--panel-soft));
  padding: 10px;
}

.slb-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.slb-header h4 {
  margin: 0;
  font-size: 14px;
  color: #ecf7ff;
}

.health {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  color: #9af3cb;
  border: 1px solid rgba(61, 222, 159, 0.4);
  background: rgba(61, 222, 159, 0.12);
}

.slb-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  min-height: 0;
}

.slb-card {
  border: 1px solid rgba(111, 244, 255, 0.16);
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.045), rgba(255, 255, 255, 0.02));
  padding: 10px;
  display: grid;
  grid-template-rows: auto auto 1fr auto;
  gap: 6px;
}

.label {
  margin: 0;
  font-size: 12px;
  color: #b6d7ef;
}

.value {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  line-height: 1;
  color: #6ff4ff;
}

.value small {
  font-size: 12px;
  color: #9ec5df;
}

.detail {
  margin: 0;
  font-size: 12px;
  color: #d7edff;
  line-height: 1.4;
}

.trend {
  margin: 0;
  font-size: 12px;
}

.trend.up {
  color: #3dde9f;
}

.trend.down {
  color: #ffd35e;
}
</style>
