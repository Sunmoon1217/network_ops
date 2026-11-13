<script setup lang="ts">
import PageLayout from '@/components/PageLayout.vue'
import DataTable from '@/components/DataTable.vue'
import DataColumn from '@/components/DataColumn.vue'
import DataPagination from '@/components/DataPagination.vue'
import { TABLE_KEYS } from '@/constants/tableKeys'
import { useCrudApi } from '@/composables/useCrudApi'
import { getDomainAssets } from '@/api/asset'

const { data, loading, search, page, pageSize, total, fetchData, refetch, pageParams, resetAndFetch } =
  useCrudApi()
const onlyInconsistent = ref(false)

const fetchAll = () =>
  fetchData(() =>
    getDomainAssets(pageParams({ inconsistent: onlyInconsistent.value ? 'true' : undefined })),
  )

watch(onlyInconsistent, resetAndFetch)
onMounted(fetchAll)
</script>

<template>
  <PageLayout title="域名资产">
    <template #actions>
      <el-switch v-model="onlyInconsistent" active-text="仅看配置不一致" />
      <el-input v-model="search" placeholder="搜索域名 / CI 标识" clearable style="width: 220px" />
    </template>
    <div class="table-wrapper">
      <DataTable :table-key="TABLE_KEYS.assetDomains" :data="data" :loading="loading">
        <DataColumn type="expand" label="">
          <template #default="{ row }">
            <div class="panel">
              <div class="panel-row"><span class="cell-k">关联 VIP：</span>{{ row.vips.join('、') || '—' }}</div>
              <div class="panel-row"><span class="cell-k">关联池：</span>{{ row.pools.join('、') || '—' }}</div>
              <div class="panel-row"><span class="cell-k">回退 IP：</span>{{ row.fallback_ips.join('、') || '—' }}</div>
              <div class="panel-row"><span class="cell-k">部署设备：</span>{{ row.devices.join('、') || '—' }}</div>
              <div v-if="row.inconsistent" class="panel-row">
                <span class="cell-k">冲突字段：</span>{{ row.conflict_fields.join('、') }}
              </div>
            </div>
          </template>
        </DataColumn>
        <DataColumn prop="fqdn" label="域名" min-width="220" show-overflow-tooltip />
        <DataColumn prop="rtypes" label="记录类型" width="120">
          <template #default="{ row }">
            <el-tag v-for="rtype in row.rtypes" :key="rtype" size="small" class="tag-gap">{{ rtype }}</el-tag>
            <span v-if="!row.rtypes.length">—</span>
          </template>
        </DataColumn>
        <DataColumn prop="lb_mode" label="负载算法" width="130" />
        <DataColumn prop="ttl" label="TTL" width="80">
          <template #default="{ row }">{{ row.ttl ?? '—' }}</template>
        </DataColumn>
        <DataColumn prop="pools" label="关联池" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.pools.join('、') || '—' }}</template>
        </DataColumn>
        <DataColumn prop="vips" label="关联 VIP" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ row.vips.join('、') || '—' }}</template>
        </DataColumn>
        <DataColumn prop="devices" label="部署设备" min-width="160" show-overflow-tooltip>
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
.tag-gap { margin-right: 4px; }
</style>
