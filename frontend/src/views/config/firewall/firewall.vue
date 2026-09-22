<script setup lang="ts">
import PageLayout from '@/layout/PageLayout.vue'
import DataTable from '@/components/DataTable.vue'
import DataPagination from '@/components/DataPagination.vue'
import FilterBar from '@/components/FilterBar.vue'
import { useCrudApi } from '@/composables/useCrudApi'
import api from '@/api/index'

const { data: natRules, loading, search, page, pageSize, total, fetchData, refetch, pageParams, resetAndFetch } =
  useCrudApi()
const filterDevice = ref<number | ''>('')

const fetchAll = () =>
  fetchData(() => api.get('/api/assets/nat-rules/', { params: pageParams({ device: filterDevice.value || undefined }) }))

watch(filterDevice, resetAndFetch)
onMounted(fetchAll)
</script>

<template>
  <PageLayout title="NAT 规则">
    <template #actions>
      <FilterBar v-model:device="filterDevice" v-model:search="search" search-placeholder="搜索规则名称" />
    </template>
    <div class="table-wrapper">
      <DataTable :data="natRules" :loading="loading">
        <el-table-column prop="device_name" label="设备" width="140" />
        <el-table-column prop="order" label="顺序" width="70" />
        <el-table-column prop="name" label="规则名称" width="160" />
        <el-table-column prop="nat_type" label="类型" width="100">
          <template #default="{ row }">
            <el-tag :type="row.nat_type === 'snat' ? 'primary' : row.nat_type === 'dnat' ? 'warning' : 'danger'" size="small">{{ row.nat_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="enabled" label="启用" width="70" align="center">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? '是' : '否' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="150" show-overflow-tooltip />
      </DataTable>
    </div>
    <DataPagination v-model:page="page" v-model:page-size="pageSize" :total="total" @change="refetch" />
  </PageLayout>
</template>

<style scoped>
.table-wrapper { flex: 1; min-height: 0; background: #fff; border-radius: 8px; overflow: hidden; }
</style>
