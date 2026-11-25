<script setup lang="ts">
import PageLayout from '@/components/PageLayout.vue'
import InspectionResults from './InspectionResults.vue'
import InspectionHistoryDrawer from './InspectionHistoryDrawer.vue'
import InspectionConfigDrawer from './InspectionConfigDrawer.vue'
import { getInspectionConfig } from '@/api/inspection'

import type { InspectionConfig } from '@/types'

const route = useRoute()
const kind = computed<'device' | 'line'>(() => (route.meta.kind === 'line' ? 'line' : 'device'))
const config = ref<InspectionConfig | null>(null)
const historyVisible = ref(false)
const configVisible = ref(false)

const formatDay = (date: Date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
const today = formatDay(new Date())
const title = computed(() => (kind.value === 'device' ? '设备巡检' : '专线巡检'))

const pad = (value: number) => String(value).padStart(2, '0')
const scheduleHint = computed(() => {
  if (!config.value) return ''
  const time = `${pad(config.value.schedule_hour)}:${pad(config.value.schedule_minute)}`
  return `每日 ${time} 巡检，采集 ${config.value.window_start.slice(0, 5)}–${config.value.window_end.slice(0, 5)} 的数据`
})

const loadConfig = async () => {
  try {
    config.value = (await getInspectionConfig()).data
  } catch {
    config.value = null
  }
}

onMounted(loadConfig)
</script>

<template>
  <PageLayout :title="title">
    <div class="inspection-head">
      <div class="head-hint">
        <span class="head-date">今天 {{ today }}</span>
        <span v-if="scheduleHint" class="head-sub">{{ scheduleHint }}</span>
      </div>
      <div class="head-actions">
        <el-button @click="historyVisible = true">历史巡检</el-button>
        <el-button type="primary" @click="configVisible = true">巡检配置</el-button>
      </div>
    </div>

    <InspectionResults :kind="kind" :date="today" table-height="calc(100vh - 330px)" />

    <InspectionHistoryDrawer v-model="historyVisible" :kind="kind" />
    <InspectionConfigDrawer v-model="configVisible" :kind="kind" @saved="loadConfig" />
  </PageLayout>
</template>

<style scoped>
.inspection-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 8px; }
.head-hint { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.head-date { font-size: 14px; font-weight: 600; }
.head-sub { font-size: 12px; color: var(--el-text-color-secondary); }
.head-actions { display: flex; gap: 8px; }
</style>
