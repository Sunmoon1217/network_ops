<script setup lang="ts">
import { fetchAllPages } from '@/utils/fetchAllPages'

const props = defineProps<{
  modelValue: number | ''
  /** 只列该类型的设备（如 slb / gslb）；不传则列全量设备 */
  deviceType?: string
}>()
const emit = defineEmits<{ (e: 'update:modelValue', v: number | ''): void; (e: 'change', v: number | ''): void }>()

const devices = ref<any[]>([])

const handleChange = (v: number | '') => {
  emit('update:modelValue', v)
  emit('change', v)
}

const loadDevices = async () => {
  try {
    // 该组件被多个列表页复用，下拉选项必须是全量（或该类型的全部）设备，分页会截断选项
    devices.value = await fetchAllPages('/api/assets/devices/', {
      ordering: 'hostname',
      ...(props.deviceType ? { device_type: props.deviceType } : {}),
    })
  } catch { /* ignore */ }
}

watch(() => props.deviceType, loadDevices)
onMounted(loadDevices)
</script>

<template>
  <el-select
    :model-value="modelValue"
    placeholder="设备"
    clearable
    filterable
    style="width: 160px"
    @update:model-value="handleChange"
  >
    <el-option v-for="d in devices" :key="d.id" :label="d.hostname" :value="d.id" />
  </el-select>
</template>
