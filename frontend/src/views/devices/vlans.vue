<script setup lang="ts">
import PageLayout from '@/ui/PageLayout.vue'
import DataTable from '@/ui/DataTable.vue'
import DeviceFilter from '@/ui/DeviceFilter.vue'
import { useCrudApi } from '@/composables/useCrudApi'
import api from '@/api/index'

const { data: vlans, loading, search, filteredData, fetchData } = useCrudApi(['vid', 'name', 'description', 'device_hostname'])
const filterDevice = ref<number | ''>('')

const displayed = computed(() => {
  if (!filterDevice.value) return filteredData.value
  return filteredData.value.filter((v: any) => v.device === filterDevice.value)
})

const fetchAll = () => {
  const params: Record<string, any> = {}
  if (filterDevice.value) params.device = filterDevice.value
  fetchData(() => api.get('/api/assets/vlans/', { params }))
}

watch(filterDevice, fetchAll)
onMounted(fetchAll)
</script>

<template>
  <PageLayout title="VLAN 管理">
    <template #actions>
      <DeviceFilter v-model="filterDevice" />
      <el-input v-model="search" placeholder="搜索 VID/名称/设备" clearable style="width: 200px" />
    </template>
    <div class="table-wrapper">
      <DataTable :data="displayed" :loading="loading">
        <el-table-column prop="vid" label="VID" width="100" sortable />
        <el-table-column prop="name" label="名称" width="180" sortable />
        <el-table-column prop="device_hostname" label="所属设备" width="150" />
        <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
      </DataTable>
    </div>
  </PageLayout>
</template>

<style scoped>
.table-wrapper { flex: 1; min-height: 0; background: #fff; border-radius: 8px; overflow: hidden; }
</style>
