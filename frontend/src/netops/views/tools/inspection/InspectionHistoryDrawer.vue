<script setup lang="ts">
import InspectionResults from './InspectionResults.vue'

const props = defineProps<{
  modelValue: boolean
  kind: 'device' | 'line'
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const dayBefore = (offset: number) => {
  const date = new Date()
  date.setDate(date.getDate() - offset)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

const historyDate = ref(dayBefore(1))
const today = dayBefore(0)
const disableFuture = (date: Date) => {
  const value = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
  return value > today
}

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})
</script>

<template>
  <el-drawer v-model="visible" :title="kind === 'device' ? '设备巡检历史' : '专线巡检历史'" size="82%">
    <div class="history-drawer">
      <div class="history-toolbar">
        <el-date-picker
          v-model="historyDate"
          type="date"
          value-format="YYYY-MM-DD"
          :clearable="false"
          :disabled-date="disableFuture"
          style="width: 180px"
        />
        <span class="hint">选择日期查看当天巡检结果，默认昨天</span>
      </div>
      <InspectionResults :kind="kind" :date="historyDate" />
    </div>
  </el-drawer>
</template>

<style scoped>
.history-drawer { display: flex; flex-direction: column; height: 100%; }
.history-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; flex-shrink: 0; }
.hint { font-size: 12px; color: var(--el-text-color-secondary); }
</style>
