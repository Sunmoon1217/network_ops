<script setup lang="ts">
import DataTable from '@/components/DataTable.vue'
import DataPagination from '@/components/DataPagination.vue'
import FilterBar from '@/components/FilterBar.vue'
import { useCrudApi } from '@/composables/useCrudApi'
import api from '@/api/index'
import type { AccessFlowItem, AccessFlowPolicyFilter, FlowAuditFlags, FlowContext } from '@/types'

/**
 * 访问流面板：策略展开后的业务流审计视图（数据源 `/api/access-flows/`，只读）。
 *
 * 与「策略列表」是两个视角：这里一行 = 一条 (源, 目的, 服务) 访问流，
 * `contexts` 列展开命中它的全部设备/策略；同一行出现
 * - 同设备多条策略 → 「设备内重复」（重复/多开）
 * - allow 与 deny 并存 → 「动作冲突」
 *
 * 过滤：设备（`?device=`，GIN 包含）、策略（`?policy=`，从策略列表「展开」带入），
 * 搜索走九字段子串（IP / 端口 / 协议）。
 */
const props = defineProps<{
  /** 从策略列表带过来的策略过滤条件；null 表示不按策略过滤 */
  policyFilter?: AccessFlowPolicyFilter | null
}>()
const emit = defineEmits<{
  (e: 'clear-policy-filter'): void
}>()

const {
  data: flows,
  loading,
  search,
  page,
  pageSize,
  total,
  fetchData,
  refetch,
  pageParams,
  resetAndFetch,
} = useCrudApi<AccessFlowItem>()

const filterDevice = ref<number | ''>('')

const fetchAll = () =>
  fetchData(() =>
    api.get('/api/access-flows/', {
      params: pageParams({
        device: filterDevice.value || undefined,
        policy: props.policyFilter?.id,
      }),
    }),
  )

watch(filterDevice, resetAndFetch)
watch(
  () => props.policyFilter,
  () => resetAndFetch(),
)
onMounted(fetchAll)

// —— 展示辅助：只接收行的属性（不接收 row 本身，Element Plus 插槽的 row 是 DefaultRow）——

/** any 哨兵：归一固定成 0.0.0.0/0（与显式的 0.0.0.0/0 子网同键） */
const isAnyAddr = (ip: string, prefix: number) => ip === '0.0.0.0' && prefix === 0

/** 地址三段 → 展示串：any / `10.1.1.1-10.1.1.9`（范围）/ `10.0.0.0/24`（前缀） */
const addrLabel = (ip: string, prefix: number, rangeEnd: string) => {
  if (isAnyAddr(ip, prefix)) return 'any'
  if (rangeEnd) return `${ip} - ${rangeEnd}`
  return `${ip}/${prefix}`
}

/** 服务三段 → 展示串：`tcp/80`、`udp/8000-8080`、无端口时只给协议（icmp / tcp / any） */
const serviceLabel = (protocol: string, port: string, port2: string) => {
  if (!port) return protocol
  return port2 ? `${protocol}/${port}-${port2}` : `${protocol}/${port}`
}

const actionLabel = (action: string) => (action === 'allow' ? '允许' : '拒绝')

const auditFlags = (contexts: Record<string, FlowContext> | undefined): FlowAuditFlags => {
  const list = Object.values(contexts ?? {})
  const perDevice = new Map<number, number>()
  let allow = false
  let deny = false
  for (const ctx of list) {
    perDevice.set(ctx.device_id, (perDevice.get(ctx.device_id) ?? 0) + 1)
    if (ctx.action === 'deny') deny = true
    else if (ctx.action === 'allow') allow = true
  }
  return {
    dupDevices: [...perDevice.values()].some((count) => count > 1),
    conflict: allow && deny,
    devices: perDevice.size,
    policies: list.length,
  }
}
</script>

<template>
  <div class="flow-panel">
    <div class="panel-filter">
      <FilterBar v-model:device="filterDevice" v-model:search="search" search-placeholder="搜索 IP/端口/协议">
        <el-tag
          v-if="policyFilter"
          type="warning"
          closable
          @close="emit('clear-policy-filter')"
        >
          策略: {{ policyFilter.label }}
        </el-tag>
      </FilterBar>
    </div>

    <div class="table-wrapper">
      <DataTable :data="flows" :loading="loading">
        <el-table-column label="源地址" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ addrLabel(row.src_ip, row.src_prefix, row.src_range_end) }}</template>
        </el-table-column>
        <el-table-column label="目的地址" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ addrLabel(row.dst_ip, row.dst_prefix, row.dst_range_end) }}</template>
        </el-table-column>
        <el-table-column label="服务" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ serviceLabel(row.protocol, row.port, row.port2) }}</template>
        </el-table-column>
        <el-table-column label="命中" width="110" align="center">
          <template #default="{ row }">
            {{ auditFlags(row.contexts).devices }} 台 / {{ auditFlags(row.contexts).policies }} 条
          </template>
        </el-table-column>
        <el-table-column label="审计" width="110" align="center">
          <template #default="{ row }">
            <el-tag v-if="auditFlags(row.contexts).conflict" type="danger" size="small">动作冲突</el-tag>
            <el-tag v-else-if="auditFlags(row.contexts).dupDevices" type="warning" size="small">设备内重复</el-tag>
            <el-tag v-else type="success" size="small">正常</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="命中明细（设备 · 策略）" min-width="300">
          <template #default="{ row }">
            <div class="ctx-list">
              <el-tag
                v-for="(ctx, key) in row.contexts"
                :key="String(key)"
                :type="ctx.action === 'deny' ? 'danger' : 'success'"
                size="small"
                effect="plain"
              >
                {{ ctx.hostname }} · {{ ctx.policy_id }}{{ ctx.name && ctx.name !== ctx.policy_id ? `(${ctx.name})` : '' }}
                · {{ actionLabel(ctx.action) }}
              </el-tag>
            </div>
          </template>
        </el-table-column>
      </DataTable>
    </div>

    <DataPagination v-model:page="page" v-model:page-size="pageSize" :total="total" @change="refetch" />
  </div>
</template>

<style scoped>
.flow-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.panel-filter {
  display: flex;
  padding: 8px 16px;
  flex-shrink: 0;
}
.table-wrapper {
  flex: 1;
  min-height: 0;
}
.ctx-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
</style>
