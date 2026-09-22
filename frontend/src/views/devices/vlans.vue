<script setup lang="ts">
import PageLayout from '@/layout/PageLayout.vue'
import DataTable from '@/components/DataTable.vue'
import DataPagination from '@/components/DataPagination.vue'
import FilterBar from '@/components/FilterBar.vue'
import { useCrudApi } from '@/composables/useCrudApi'
import api from '@/api/index'

const { data: vlans, loading, search, page, pageSize, total, fetchData, refetch, pageParams, resetAndFetch } =
  useCrudApi()
const filterDevice = ref<number | ''>('')

const fetchAll = () =>
  fetchData(() => api.get('/api/assets/vlans/', { params: pageParams({ device: filterDevice.value || undefined }) }))

watch(filterDevice, resetAndFetch)
onMounted(fetchAll)
</script>

<template>
  <PageLayout title="VLAN 管理">
    <template #actions>
      <FilterBar v-model:device="filterDevice" v-model:search="search" search-placeholder="搜索 VID/名称/设备" />
    </template>
    <div class="table-wrapper">
      <DataTable :data="vlans" :loading="loading">
        <el-table-column prop="vid" label="VID" width="100" sortable />
        <el-table-column prop="name" label="名称" width="180" sortable />
        <el-table-column prop="device_hostname" label="所属设备" width="150" />
        <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
      </DataTable>
    </div>
    <DataPagination v-model:page="page" v-model:page-size="pageSize" :total="total" @change="refetch" />
  </PageLayout>
</template>

<style scoped>
.table-wrapper { flex: 1; min-height: 0; background: #fff; border-radius: 8px; overflow: hidden; }
</style>
