<script setup lang="ts">
import PageLayout from '@/ui/PageLayout.vue'
import DataTable from '@/ui/DataTable.vue'
import DataPagination from '@/ui/DataPagination.vue'
import DeviceFilter from '@/ui/DeviceFilter.vue'
import { useCrudApi } from '@/composables/useCrudApi'
import { protocolTagType } from '@/composables/useTagType'
import api from '@/api/index'

const { data: routes, loading, search, page, pageSize, total, fetchData, refetch, pageParams, resetAndFetch } =
  useCrudApi()
const filterDevice = ref<number | ''>('')
const filterProtocol = ref('')

const protocolOptions = [
  { label: '静态', value: 'static' },
  { label: '直连', value: 'connected' },
  { label: 'OSPF', value: 'ospf' },
  { label: 'BGP', value: 'bgp' },
]

const fetchAll = () =>
  fetchData(() =>
    api.get('/api/assets/routes/', {
      params: pageParams({
        device: filterDevice.value || undefined,
        protocol: filterProtocol.value || undefined,
      }),
    })
  )

watch(filterDevice, resetAndFetch)
watch(filterProtocol, resetAndFetch)
onMounted(fetchAll)
</script>

<template>
  <PageLayout title="路由表">
    <template #actions>
      <DeviceFilter v-model="filterDevice" />
      <el-select v-model="filterProtocol" placeholder="协议" clearable style="width: 100px">
        <el-option v-for="p in protocolOptions" :key="p.value" :label="p.label" :value="p.value" />
      </el-select>
      <el-input v-model="search" placeholder="搜索" clearable style="width: 180px" />
    </template>
    <div class="table-wrapper">
      <DataTable :data="routes" :loading="loading">
        <el-table-column prop="device_hostname" label="设备" width="140" sortable />
        <el-table-column prop="vrf_name" label="VRF" width="100" />
        <el-table-column prop="destination" label="目的网段" width="160" />
        <el-table-column prop="nexthop" label="下一跳" width="140" />
        <el-table-column prop="interface" label="出接口" width="150" />
        <el-table-column prop="protocol" label="协议" width="90">
          <template #default="{ row }">
            <el-tag :type="protocolTagType(row.protocol)" size="small">{{ row.protocol }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="metric" label="度量值" width="80" />
      </DataTable>
    </div>
    <DataPagination v-model:page="page" v-model:page-size="pageSize" :total="total" @change="refetch" />
  </PageLayout>
</template>

<style scoped>
.table-wrapper { flex: 1; min-height: 0; background: #fff; border-radius: 8px; overflow: hidden; }
</style>
