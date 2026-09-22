<script setup lang="ts">
import PageLayout from '@/layout/PageLayout.vue'
import DataTable from '@/components/DataTable.vue'
import DataPagination from '@/components/DataPagination.vue'
import FilterBar from '@/components/FilterBar.vue'
import { useCrudApi } from '@/composables/useCrudApi'
import { useSearchSync } from '@/composables/useSearchSync'
import { getGtmWideips, getGtmPools } from '@/api/config'

const activeTab = ref('wideip')
const filterDevice = ref<number | ''>('')

// Wide IP 与 Pool 各自持有独立的分页、搜索与加载状态
const {
  data: wideips, loading: wideipLoading, page: wideipPage, pageSize: wideipPageSize,
  total: wideipTotal, fetchData: fetchWideipData, refetch: refetchWideips, pageParams: wideipPageParams,
  resetAndFetch: resetWideips, search: wideipSearch,
} = useCrudApi()
const {
  data: pools, loading: poolLoading, page: poolPage, pageSize: poolPageSize,
  total: poolTotal, fetchData: fetchPoolData, refetch: refetchPools, pageParams: poolPageParams,
  resetAndFetch: resetPool, search: poolSearch,
} = useCrudApi()

// 页面级共享搜索词：同步写入两个 tab 的 search，变化由 useCrudApi 内部防抖重新请求
const keyword = useSearchSync(wideipSearch, poolSearch)

// fetcher 内用各自的 pageParams 拼装分页参数，设备筛选走服务端 device 查询参数
const loadWideips = () =>
  fetchWideipData(() => getGtmWideips(wideipPageParams({ device: filterDevice.value || undefined })))

const loadPools = () =>
  fetchPoolData(() => getGtmPools(poolPageParams({ device: filterDevice.value || undefined })))

// 设备筛选变化时两个表格都回到第 1 页并重新拉取
const handleDeviceChange = () => {
  resetWideips()
  resetPool()
}

watch(filterDevice, handleDeviceChange)
onMounted(() => {
  loadWideips()
  loadPools()
})
</script>

<template>
  <PageLayout title="域名解析管理">
    <template #actions>
      <FilterBar
        v-model:device="filterDevice"
        v-model:search="keyword"
        device-type="gslb"
        search-placeholder="搜索域名/池/设备"
        search-width="220px"
      />
    </template>
    <el-tabs v-model="activeTab" class="page-tabs">
      <el-tab-pane label="Wide IP" name="wideip">
        <div class="table-wrapper">
          <DataTable :data="wideips" :loading="wideipLoading" size="small">
            <el-table-column prop="device_hostname" label="设备" width="140" sortable />
            <el-table-column prop="name" label="域名" width="220" sortable />
            <el-table-column prop="rtype" label="记录类型" width="100" />
            <el-table-column prop="lb_mode" label="负载模式" width="120" />
            <el-table-column prop="pools" label="关联池" min-width="200">
              <template #default="{ row }">
                <el-tag v-for="p in (row.pools || [])" :key="p" size="small" style="margin-right: 4px">{{ p }}</el-tag>
                <span v-if="!row.pools?.length" style="color: #c0c4cc">-</span>
              </template>
            </el-table-column>
          </DataTable>
        </div>
        <DataPagination
          v-model:page="wideipPage"
          v-model:page-size="wideipPageSize"
          :total="wideipTotal"
          @change="refetchWideips"
        />
      </el-tab-pane>
      <el-tab-pane label="Pool" name="pool">
        <div class="table-wrapper">
          <DataTable :data="pools" :loading="poolLoading" size="small">
            <el-table-column prop="device_hostname" label="设备" width="140" sortable />
            <el-table-column prop="name" label="名称" width="180" sortable />
            <el-table-column prop="lb_mode" label="负载模式" width="120" />
            <el-table-column prop="alternate_mode" label="备选模式" width="120" />
            <el-table-column prop="fallback_mode" label="回退模式" width="120" />
            <el-table-column prop="fallback_ip" label="回退IP" width="140" />
            <el-table-column prop="ttl" label="TTL" width="70" />
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
