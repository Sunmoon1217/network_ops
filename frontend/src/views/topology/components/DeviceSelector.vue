<script setup lang="ts">
import { ref } from 'vue'
import { getDevices } from '@/api/devices'

defineProps<{ visible: boolean }>()
const emit = defineEmits<{
  select: [device: any]
  'update:visible': [value: boolean]
}>()

const search = ref('')
const devices = ref<any[]>([])
const loading = ref(false)

const fetchDevices = async () => {
  loading.value = true
  try {
    const res = await getDevices({ search: search.value, page_size: 50 })
    devices.value = res.data.results || res.data
  } finally {
    loading.value = false
  }
}

const handleSelect = (device: any) => {
  emit('select', device)
}
</script>

<template>
  <el-dialog
    title="选择设备"
    :model-value="visible"
    width="600px"
    @update:model-value="emit('update:visible', $event)"
    @open="fetchDevices"
  >
    <el-input
      v-model="search"
      placeholder="搜索设备名称..."
      clearable
      @input="fetchDevices"
    />
    <el-table
      :data="devices"
      v-loading="loading"
      style="width: 100%; margin-top: 12px"
      @row-dblclick="handleSelect"
    >
      <el-table-column prop="hostname" label="主机名" />
      <el-table-column prop="device_type_display" label="类型" width="120" />
      <el-table-column prop="idc_name" label="数据中心" width="120" />
      <el-table-column label="操作" width="80" align="center">
        <template #default="{ row }">
          <el-button type="primary" link @click="handleSelect(row)">选择</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>
</template>
