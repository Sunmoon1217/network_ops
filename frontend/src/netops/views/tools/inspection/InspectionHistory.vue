<script setup lang="ts">
import PageLayout from '@/components/PageLayout.vue'
import InspectionResults from './InspectionResults.vue'

const router = useRouter()
const route = useRoute()

const kind = computed<'device' | 'line'>(() => (route.query.kind === 'line' ? 'line' : 'device'))

const dayBefore = (offset: number) => {
  const d = new Date()
  d.setDate(d.getDate() - offset)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
const today = dayBefore(0)
const disableFuture = (date: Date) => {
  const v = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
  return v > today
}

const defaultDate = dayBefore(1)
const historyDate = ref<string>(defaultDate)

const title = computed(() => (kind.value === 'device' ? '设备巡检历史' : '专线巡检历史'))

const switchKind = (v: string | number | boolean | undefined) => {
  const kindVal = v === 'line' ? 'line' : 'device'
  router.push({ path: '/tools/inspection/history', query: { ...route.query, kind: kindVal } })
}
const goDetail = () => router.push(kind.value === 'device' ? '/tools/inspection/device' : '/tools/inspection/line')
const goOverview = () => router.push('/tools/inspection')

const reset = () => { historyDate.value = defaultDate }
</script>

<template>
  <PageLayout :title="title">
    <div class="history-page">
      <div class="page-head">
        <div class="head-left">
          <el-button link type="primary" @click="goOverview">← 返回巡检总览</el-button>
          <el-radio-group :model-value="kind" @update:model-value="switchKind" size="small">
            <el-radio-button value="device">设备巡检</el-radio-button>
            <el-radio-button value="line">专线巡检</el-radio-button>
          </el-radio-group>
        </div>
        <div class="head-right">
          <el-button @click="goDetail">查看今日详情</el-button>
        </div>
      </div>

      <div class="page-toolbar">
        <span class="tb-label">选择日期：</span>
        <el-date-picker
          v-model="historyDate"
          type="date"
          value-format="YYYY-MM-DD"
          :clearable="false"
          :disabled-date="disableFuture"
          style="width: 180px"
        />
        <el-button size="small" @click="reset">重置</el-button>
        <span class="tb-hint">默认昨天；历史结果仅展示采集日期当天的窗口内数据</span>
      </div>

      <InspectionResults :kind="kind" :date="historyDate" />
    </div>
  </PageLayout>
</template>

<style scoped>
.history-page { display: flex; flex-direction: column; flex: 1; min-height: 0; gap: 10px; }
.page-head { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; flex-shrink: 0; }
.head-left { display: flex; align-items: center; gap: 12px; }
.page-toolbar { display: flex; align-items: center; gap: 10px; flex-shrink: 0; background: var(--el-bg-color); border-radius: 8px; padding: 10px 14px; border: 1px solid var(--el-border-color-lighter); }
.tb-label { font-size: 12px; color: var(--el-text-color-secondary); }
.tb-hint { font-size: 12px; color: var(--el-text-color-secondary); margin-left: auto; }
</style>
