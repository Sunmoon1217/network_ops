<script setup lang="ts">
import PageLayout from '@/layout/PageLayout.vue'
import DataTable from '@/components/DataTable.vue'
import DataPagination from '@/components/DataPagination.vue'
import DeviceFilter from '@/components/DeviceFilter.vue'
import { useCrudApi } from '@/composables/useCrudApi'
import { getLtmVirtualServers, getLtmPools } from '@/api/config'

const activeTab = ref('vs')
const filterDevice = ref<number | ''>('')

// Virtual Server 与 Pool 各自持有独立的分页、搜索与加载状态
const {
  data: virtualServers, loading: vsLoading, page: vsPage, pageSize: vsPageSize,
  total: vsTotal, fetchData: fetchVsData, refetch: refetchVs, pageParams: vsPageParams,
  resetAndFetch: resetVs,
} = useCrudApi()
const {
  data: pools, loading: poolLoading, page: poolPage, pageSize: poolPageSize,
  total: poolTotal, fetchData: fetchPoolData, refetch: refetchPools, pageParams: poolPageParams,
  resetAndFetch: resetPool,
} = useCrudApi()

// fetcher 内用各自的 pageParams 拼装分页参数，设备筛选走服务端 device 查询参数
const loadVirtualServers = () =>
  fetchVsData(() => getLtmVirtualServers(vsPageParams({ device: filterDevice.value || undefined })))

const loadPools = () =>
  fetchPoolData(() => getLtmPools(poolPageParams({ device: filterDevice.value || undefined })))

// 设备筛选变化时两个表格都回到第 1 页并重新拉取
const handleDeviceChange = () => {
  resetVs()
  resetPool()
}

watch(filterDevice, handleDeviceChange)
onMounted(() => {
  loadVirtualServers()
  loadPools()
})
</script>

<template>
  <PageLayout title="负载均衡管理">
    <template #actions>
      <DeviceFilter v-model="filterDevice" />
    </template>
    <el-tabs v-model="activeTab" class="page-tabs">
      <el-tab-pane label="Virtual Server" name="vs">
        <div class="table-wrapper">
          <DataTable :data="virtualServers" :loading="vsLoading" size="small">
            <el-table-column prop="device_hostname" label="设备" width="140" sortable />
            <el-table-column prop="name" label="名称" width="180" sortable />
            <el-table-column prop="vs_address" label="虚拟地址" width="140" />
            <el-table-column prop="vs_port" label="端口" width="80" />
            <el-table-column prop="protocol" label="协议" width="80" />
            <el-table-column prop="pool" label="关联池" width="140" />
            <el-table-column prop="snat_type" label="SNAT" width="100" />
            <el-table-column prop="persist" label="会话保持" width="100" />
          </DataTable>
        </div>
        <DataPagination
          v-model:page="vsPage"
          v-model:page-size="vsPageSize"
          :total="vsTotal"
          @change="refetchVs"
        />
      </el-tab-pane>
      <el-tab-pane label="Pool" name="pool">
        <div class="table-wrapper">
          <DataTable :data="pools" :loading="poolLoading" size="small">
            <el-table-column prop="device_hostname" label="设备" width="140" sortable />
            <el-table-column prop="name" label="名称" width="180" sortable />
            <el-table-column prop="mode" label="负载模式" width="120" />
            <el-table-column prop="monitors" label="监控" min-width="200">
              <template #default="{ row }">
                <el-tag v-for="m in (row.monitors || [])" :key="m" size="small" style="margin-right: 4px">{{ m }}</el-tag>
                <span v-if="!row.monitors?.length" style="color: #c0c4cc">-</span>
              </template>
            </el-table-column>
          </DataTable>
        </div>
        <DataPagination
          v-model:page="poolPage"
          v-model:page-size="poolPageSize"
          :total="poolTotal"
          @change="refetchPools"
        />
      </el-tab-pane>
    </el-tabs>
  </PageLayout>
</template>

<style scoped>
.page-tabs { flex: 1; min-height: 0; }
.page-tabs :deep(.el-tabs__content) { display: flex; flex-direction: column; }
.page-tabs :deep(.el-tab-pane) { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.table-wrapper { flex: 1; min-height: 0; background: #fff; border-radius: 8px; overflow: hidden; }
</style>
