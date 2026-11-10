<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getDashboard } from '@/api/dashboard'
import { useInterval } from '@dashboard/utils/timer'

const EMPTY = '--'
const instance = ref<number | null>(null)
const listener = ref<number | null>(null)
const collected = ref(false)
const loadError = ref('')

const num = (value: unknown): number | null => {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '' && Number.isFinite(Number(value))) return Number(value)
  return null
}

const cards = computed(() => [
  { label: 'SLB 实例总数', value: instance.value, detail: 'Autotask 接口采集' },
  { label: 'SLB 监听总数', value: listener.value, detail: 'TCP / HTTP / HTTPS 监听' },
])

const fetchData = async () => {
  try {
    // 采集器写 slb/slb/slb，list_value[0] = {instance, listener}
    const rows = await getDashboard({ panel: 'slb', group: 'slb' })
    const data = rows.find((row) => row.name === 'slb')?.list_value?.[0]
    instance.value = num(data?.instance)
    listener.value = num(data?.listener)
    collected.value = Boolean(data)
    loadError.value = ''
  } catch (error) {
    console.error('[dashboard] SLB 数据获取失败:', error)
    loadError.value = 'SLB 数据获取失败'
  }
}

const { start } = useInterval(fetchData, 5 * 60 * 1000, true)

onMounted(() => {
  start()
})
</script>

<template>
  <div class="cloud-slb">
    <div class="slb-header">
      <h4>云平台负载均衡状态</h4>
      <span class="health" :class="collected ? 'ok' : 'muted'">
        {{ loadError || (collected ? '已采集' : '暂无数据') }}
      </span>
    </div>
    <div class="slb-grid">
      <article v-for="item in cards" :key="item.label" class="slb-card">
        <p class="label">{{ item.label }}</p>
        <p class="value">{{ item.value ?? EMPTY }} <small>个</small></p>
        <p class="detail">{{ item.detail }}</p>
      </article>
    </div>
  </div>
</template>

<style scoped>
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

.slb-header { display: flex; justify-content: space-between; align-items: center; }
.slb-header h4 { margin: 0; font-size: 14px; color: #ecf7ff; }

.health {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  border: 1px solid transparent;
}

.health.ok { color: #9af3cb; border-color: rgba(61, 222, 159, 0.4); background: rgba(61, 222, 159, 0.12); }
.health.muted { color: #9fb6cc; border-color: rgba(159, 182, 204, 0.3); background: rgba(159, 182, 204, 0.1); }

.slb-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; min-height: 0; }

.slb-card {
  border: 1px solid rgba(111, 244, 255, 0.16);
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.045), rgba(255, 255, 255, 0.02));
  padding: 10px;
  display: grid;
  grid-template-rows: auto auto 1fr;
  gap: 6px;
}

.label { margin: 0; font-size: 12px; color: #b6d7ef; }
.value { margin: 0; font-size: 24px; font-weight: 700; line-height: 1; color: #6ff4ff; }
.value small { font-size: 12px; color: #9ec5df; }
.detail { margin: 0; font-size: 12px; color: #d7edff; line-height: 1.4; }
</style>
