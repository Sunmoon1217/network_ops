<script setup lang="ts">
import PageLayout from '@/layout/PageLayout.vue'
import DataTable from '@/components/DataTable.vue'
import DataPagination from '@/components/DataPagination.vue'
import FilterBar from '@/components/FilterBar.vue'
import { useCrudApi } from '@/composables/useCrudApi'
import api from '@/api/index'

const { data: policies, loading, search, page, pageSize, total, fetchData, refetch, pageParams, resetAndFetch } =
  useCrudApi()
const filterDevice = ref<number | ''>('')

const fetchAll = () =>
  fetchData(() => api.get('/api/assets/policies/', { params: pageParams({ device: filterDevice.value || undefined }) }))

watch(filterDevice, resetAndFetch)
onMounted(fetchAll)
</script>

<template>
  <PageLayout title="访问策略">
    <template #actions>
      <FilterBar v-model:device="filterDevice" v-model:search="search" search-placeholder="搜索策略名称/ID" />
    </template>
    <div class="table-wrapper">
      <DataTable :data="policies" :loading="loading">
        <el-table-column prop="device_name" label="设备" width="140" />
        <el-table-column prop="policy_id" label="策略ID" width="100" />
        <el-table-column prop="order" label="顺序" width="70" />
        <el-table-column prop="name" label="策略名称" width="160" />
        <el-table-column prop="action" label="动作" width="80">
          <template #default="{ row }">
            <el-tag :type="row.action === 'allow' ? 'success' : 'danger'" size="small">{{ row.action }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="enabled" label="启用" width="70" align="center">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? '是' : '否' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="log" label="日志" width="60" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.log" type="warning" size="small">开</el-tag>
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
