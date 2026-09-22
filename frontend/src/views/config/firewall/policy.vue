<script setup lang="ts">
import PageLayout from '@/layout/PageLayout.vue'
import DataTable from '@/components/DataTable.vue'
import DataPagination from '@/components/DataPagination.vue'
import FilterBar from '@/components/FilterBar.vue'
import AccessFlowPanel from './AccessFlowPanel.vue'
import { useCrudApi } from '@/composables/useCrudApi'
import api from '@/api/index'
import type { AccessFlowPolicyFilter, PolicyItem } from '@/types'

const {
  data: policies,
  loading,
  search,
  page,
  pageSize,
  total,
  fetchData,
  refetch,
  pageParams,
  resetAndFetch,
} = useCrudApi<PolicyItem>()
const filterDevice = ref<number | ''>('')

/**
 * 页内标签页：策略列表（管理视角，一条策略一行）/ 访问流（审计视角，展开后的
 * 业务流一行）——同一份策略数据的两种粒度，不进导航、并列互达。
 */
const activeTab = ref<'policy' | 'flows'>('policy')

/** 从策略行「展开」带来的访问流过滤条件（id 是 Policy 主键，对接 ?policy=） */
const flowPolicy = ref<AccessFlowPolicyFilter | null>(null)

const fetchAll = () =>
  fetchData(() => api.get('/api/assets/policies/', { params: pageParams({ device: filterDevice.value || undefined }) }))

/** 策略行 → 访问流标签页，并按该策略过滤命中的访问流 */
const openFlows = (id: number, name: string, policyId: string) => {
  flowPolicy.value = { id, label: name || policyId }
  activeTab.value = 'flows'
}

const actionLabel = (action: string) => (action === 'allow' ? '允许' : '拒绝')
/** 后端已格式化成字符串数组，这里只负责拼接展示（地址簿引用形如 `office(10.0.0.0/24)`） */
const joinList = (items: string[] | undefined) => (items && items.length ? items.join('、') : 'any')

watch(filterDevice, resetAndFetch)
onMounted(fetchAll)
</script>

<template>
  <PageLayout title="访问策略">
    <template #actions>
      <FilterBar
        v-if="activeTab === 'policy'"
        v-model:device="filterDevice"
        v-model:search="search"
        search-placeholder="搜索策略名称/ID"
      />
    </template>

    <div class="content">
      <div class="tabs-bar">
        <el-tabs v-model="activeTab">
          <el-tab-pane label="策略列表" name="policy" />
          <el-tab-pane label="访问流" name="flows" />
        </el-tabs>
      </div>

      <template v-if="activeTab === 'policy'">
        <div class="table-wrapper">
          <DataTable :data="policies" :loading="loading">
            <el-table-column prop="device_hostname" label="设备" width="140" />
            <el-table-column prop="policy_id" label="策略ID" width="100" />
            <el-table-column prop="name" label="策略名称" width="150" show-overflow-tooltip />
            <el-table-column prop="action" label="动作" width="80" align="center">
              <template #default="{ row }">
                <el-tag :type="row.action === 'allow' ? 'success' : 'danger'" size="small">
                  {{ actionLabel(row.action) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="source_addresses_display" label="源地址" min-width="160" show-overflow-tooltip>
              <template #default="{ row }">{{ joinList(row.source_addresses_display) }}</template>
            </el-table-column>
            <el-table-column prop="destination_addresses_display" label="目的地址" min-width="160" show-overflow-tooltip>
              <template #default="{ row }">{{ joinList(row.destination_addresses_display) }}</template>
            </el-table-column>
            <el-table-column prop="services_display" label="端口" min-width="130" show-overflow-tooltip>
              <template #default="{ row }">{{ joinList(row.services_display) }}</template>
            </el-table-column>
            <el-table-column prop="enabled" label="状态" width="80" align="center">
              <template #default="{ row }">
                <el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? '启用' : '停用' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="log" label="日志" width="70" align="center">
              <template #default="{ row }">
                <el-tag :type="row.log ? 'warning' : 'info'" size="small">{{ row.log ? '开' : '关' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80" align="center" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openFlows(row.id, row.name, row.policy_id)">展开</el-button>
              </template>
            </el-table-column>
          </DataTable>
        </div>
        <DataPagination v-model:page="page" v-model:page-size="pageSize" :total="total" @change="refetch" />
      </template>

      <AccessFlowPanel
        v-else
        :policy-filter="flowPolicy"
        @clear-policy-filter="flowPolicy = null"
      />
    </div>
  </PageLayout>
</template>

<style scoped>
.content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
}
.tabs-bar {
  flex-shrink: 0;
  padding: 0 16px;
}
.tabs-bar :deep(.el-tabs__header) {
  margin-bottom: 8px;
}
.table-wrapper {
  flex: 1;
  min-height: 0;
}
</style>
