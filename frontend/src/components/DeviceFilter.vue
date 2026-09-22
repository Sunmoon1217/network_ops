<script setup lang="ts">
import { fetchAllPages } from '@/utils/fetchAllPages'

const props = defineProps<{ modelValue: number | '' }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: number | ''): void; (e: 'change', v: number | ''): void }>()

const devices = ref<any[]>([])

const handleChange = (v: number | '') => {
  emit('update:modelValue', v)
  emit('change', v)
}

onMounted(async () => {
  try {
    // 该组件被多个列表页复用，下拉选项必须是全量设备，分页会截断选项
    devices.value = await fetchAllPages('/api/assets/devices/', { ordering: 'hostname' })
  } catch { /* ignore */ }
})
</script>

<template>
  <el-select :model-value="modelValue" placeholder="设备" clearable style="width: 140px" @update:model-value="handleChange">
    <el-option v-for="d in devices" :key="d.id" :label="d.hostname" :value="d.id" />
  </el-select>
</template>
