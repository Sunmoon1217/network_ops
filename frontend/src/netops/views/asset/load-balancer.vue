<script setup lang="ts">
import PageLayout from '@/components/PageLayout.vue'
import DataTable from '@/components/DataTable.vue'
import DataColumn from '@/components/DataColumn.vue'
import DataPagination from '@/components/DataPagination.vue'
import { TABLE_KEYS } from '@/constants/tableKeys'
import { useCrudApi } from '@/composables/useCrudApi'
import { getLoadBalancerServices } from '@/api/asset'

const { data, loading, search, page, pageSize, total, fetchData, refetch, pageParams, resetAndFetch } =
  useCrudApi()
const onlyInconsistent = ref(false)
const filterStatus = ref('')

const statusOptions = [
  { label: '启用', value: 'enabled' },
  { label: '停用', value: 'disabled' },
]

const fetchAll = () =>
  fetchData(() =>
    getLoadBalancerServices(
      pageParams({
        inconsistent: onlyInconsistent.value ? 'true' : undefined,
        status: filterStatus.value || undefined,
      }),
    ),
  )

watch([onlyInconsistent, filterStatus], resetAndFetch)
onMounted(fetchAll)
</script>

<template>
  <PageLayout title="负载均衡资产">
    <template #actions>
      <el-select v-model="filterStatus" placeholder="状态" clearable style="width: 110px">
        <el-option v-for="status in statusOptions" :key="status.value" :label="status.label" :value="status.value" />
      </el-select>
      <el-switch v-model="onlyInconsistent" active-text="仅看配置不一致" />
      <el-input v-model="search" placeholder="搜索 VIP / 端口 / CI 标识" clearable style="width: 230px" />
    </template>
    <div class="table-wrapper">
      <DataTable :table-key="TABLE_KEYS.assetLoadBalancers" :data="data" :loading="loading">
        <DataColumn type="expand" label="">
          <template #default="{ row }">
            <div class="panel">
              <div class="panel-row"><span class="cell-k">关联池：</span>{{ row.pools.join('、') || '—' }}</div>
              <div class="panel-row"><span class="cell-k">Profile：</span>{{ row.profiles.join('、') || '—' }}</div>
              <div class="panel-row"><span class="cell-k">iRule：</span>{{ row.rules.join('、') || '—' }}</div>
              <div class="panel-row"><span class="cell-k">部署设备：</span>{{ row.devices.join('、') || '—' }}</div>
              <div v-if="row.inconsistent" class="panel-row">
                <span class="cell-k">冲突字段：</span>{{ row.conflict_fields.join('、') }}
              </div>
            </div>
          </template>
        </DataColumn>
        <DataColumn prop="asset_key" label="VIP#端口" min-width="200" show-overflow-tooltip />
        <DataColumn prop="protocol" label="协议" width="90">
          <template #default="{ row }">{{ row.protocol || '—' }}</template>
        </DataColumn>
        <DataColumn prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'enabled' ? 'success' : 'info'" size="small">
              {{ row.status || '—' }}
            </el-tag>
          </template>
        </DataColumn>
        <DataColumn prop="pools" label="关联池" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.pools.join('、') || '—' }}</template>
        </DataColumn>
        <DataColumn prop="member_count" label="成员数" width="90" />
        <DataColumn prop="devices" label="部署设备" min-width="170" show-overflow-tooltip>
          <template #default="{ row }">{{ row.devices.join('、') || '—' }}</template>
        </DataColumn>
        <DataColumn prop="inconsistent" label="一致性" width="100">
          <template #default="{ row }">
            <el-tag :type="row.inconsistent ? 'warning' : 'success'" size="small">
              {{ row.inconsistent ? '不一致' : '一致' }}
            </el-tag>
          </template>
        </DataColumn>
        <DataColumn prop="ci_id" label="CI 标识" width="150" />
      </DataTable>
    </div>
    <DataPagination v-model:page="page" v-model:page-size="pageSize" :total="total" @change="refetch" />
  </PageLayout>
</template>

<style scoped>
.table-wrapper { flex: 1; min-height: 0; background: var(--el-bg-color); border-radius: 8px; overflow: hidden; }
.panel { padding: 4px 0 4px 48px; }
.panel-row { line-height: 24px; color: var(--el-text-color-regular); }
.cell-k { color: var(--el-text-color-secondary); }
</style>
