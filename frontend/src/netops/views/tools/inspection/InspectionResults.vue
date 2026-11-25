<script setup lang="ts">
import DataTable from '@/components/DataTable.vue'
import DataColumn from '@/components/DataColumn.vue'
import DataPagination from '@/components/DataPagination.vue'
import StatCard from '@/components/StatCard.vue'
import { TABLE_KEYS } from '@/constants/tableKeys'
import { useCrudApi } from '@/composables/useCrudApi'
import {
  getInspectionDevices,
  getInspectionInterfaces,
  getInspectionRuns,
  getInspectionSummary,
} from '@/api/inspection'

import type { InspectionDeviceMetric, InspectionDeviceSummary, InspectionInterfaceMetric, InspectionRun } from '@/types'

const props = withDefaults(
  defineProps<{
    kind: 'device' | 'line'
    date: string
    tableHeight?: string
  }>(),
  { tableHeight: '420px' },
)

const isDevice = computed(() => props.kind === 'device')
const run = ref<InspectionRun | null>(null)
const runLoading = ref(false)
const summary = ref<InspectionDeviceSummary | null>(null)
const summaryLoading = ref(false)

const {
  data: devices,
  loading: devicesLoading,
  page: devicePage,
  pageSize: devicePageSize,
  total: deviceTotal,
  fetchData: fetchDevices,
  refetch: refetchDevices,
} = useCrudApi<InspectionDeviceMetric>()

const {
  data: interfaces,
  loading: interfacesLoading,
  page: interfacePage,
  pageSize: interfacePageSize,
  total: interfaceTotal,
  fetchData: fetchInterfaces,
  refetch: refetchInterfaces,
} = useCrudApi<InspectionInterfaceMetric>()

const loading = computed(() => runLoading.value || summaryLoading.value || devicesLoading.value || interfacesLoading.value)

const loadRun = async () => {
  runLoading.value = true
  try {
    run.value = (await getInspectionRuns({ date: props.date, page_size: 1 })).data.results[0] ?? null
  } catch {
    run.value = null
  } finally {
    runLoading.value = false
  }
}

const load = async () => {
  await loadRun()
  if (isDevice.value) {
    summaryLoading.value = true
    try {
      summary.value = (await getInspectionSummary({ date: props.date })).data
    } catch {
      summary.value = null
    } finally {
      summaryLoading.value = false
    }
    devicePage.value = 1
    await fetchDevices(() => getInspectionDevices({ date: props.date, page: devicePage.value, page_size: devicePageSize.value }))
  } else {
    interfacePage.value = 1
    await fetchInterfaces(() => getInspectionInterfaces({ date: props.date, page: interfacePage.value, page_size: interfacePageSize.value }))
  }
}

watch(() => [props.kind, props.date], load)
onMounted(load)

const fmtPct = (value: number | null) => (value == null ? '—' : `${value}%`)

/** 带宽统一换算到 Kbps / Mbps / Gbps，便于阅读 */
const fmtBps = (value: number | null) => {
  if (value == null) return '—'
  const units = [
    { size: 1e9, label: 'Gbps' },
    { size: 1e6, label: 'Mbps' },
    { size: 1e3, label: 'Kbps' },
  ]
  const hit = units.find((unit) => value >= unit.size)
  return hit ? `${(value / hit.size).toFixed(2)} ${hit.label}` : `${value.toFixed(0)} bps`
}

const usageTagType = (value: number | null) => {
  if (value == null) return 'info'
  if (value >= 80) return 'danger'
  if (value >= 60) return 'warning'
  return 'success'
}

const fmtTime = (value: string | null) => (value ? value.replace('T', ' ').slice(0, 19) : '—')

const cards = computed(() => {
  if (isDevice.value) {
    return [
      { label: '巡检状态', value: run.value ? (run.value.status === 'success' ? '成功' : '失败') : '未执行' },
      { label: '设备数', value: summary.value?.device_count ?? 0 },
      { label: 'CPU 日均', value: fmtPct(summary.value?.cpu_avg ?? null) },
      { label: '内存日均', value: fmtPct(summary.value?.memory_avg ?? null) },
    ]
  }
  return [
    { label: '巡检状态', value: run.value ? (run.value.status === 'success' ? '成功' : '失败') : '未执行' },
    { label: '专线接口数', value: interfaceTotal.value },
    { label: '完成时间', value: fmtTime(run.value?.finished_at ?? null) },
    { label: '数据日期', value: props.date },
  ]
})
</script>

<template>
  <div class="results">
    <el-alert
      v-if="!run && !runLoading"
      type="info"
      :closable="false"
      show-icon
      title="该日期暂无巡检批次"
      description="可能尚未到巡检时间；可在「巡检配置」中调整巡检时间点与时间范围。"
      class="run-alert"
    />
    <el-alert
      v-else-if="run?.status === 'failed'"
      type="error"
      :closable="false"
      show-icon
      :title="`巡检失败：${run.error || '未知错误'}`"
      class="run-alert"
    />

    <div class="stat-row">
      <StatCard v-for="card in cards" :key="card.label" :label="card.label" :value="card.value" />
    </div>

    <div v-if="isDevice && summary?.cpu_top.length" class="top-line">
      <span class="top-label">CPU 峰值 TOP5：</span>
      <el-tag v-for="row in summary.cpu_top" :key="row.name" size="small" :type="usageTagType(row.cpu_max)">
        {{ row.name }} {{ fmtPct(row.cpu_max) }}
      </el-tag>
    </div>

    <div class="table-box" :style="{ height: tableHeight }">
      <DataTable
        v-if="isDevice"
        :table-key="TABLE_KEYS.inspectionDevices"
        :data="devices"
        :loading="loading"
        size="small"
      >
        <DataColumn prop="host" label="主机" min-width="180" show-overflow-tooltip />
        <DataColumn prop="cpu_avg" label="CPU 日均" width="110">
          <template #default="{ row }">{{ fmtPct(row.cpu_avg) }}</template>
        </DataColumn>
        <DataColumn prop="cpu_max" label="CPU 峰值" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="usageTagType(row.cpu_max)">{{ fmtPct(row.cpu_max) }}</el-tag>
          </template>
        </DataColumn>
        <DataColumn prop="memory_avg" label="内存日均" width="110">
          <template #default="{ row }">{{ fmtPct(row.memory_avg) }}</template>
        </DataColumn>
        <DataColumn prop="memory_max" label="内存峰值" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="usageTagType(row.memory_max)">{{ fmtPct(row.memory_max) }}</el-tag>
          </template>
        </DataColumn>
        <DataColumn prop="date" label="业务日期" width="120" />
        <DataColumn prop="updated_at" label="落库时间" width="170">
          <template #default="{ row }">{{ fmtTime(row.updated_at) }}</template>
        </DataColumn>
      </DataTable>

      <DataTable
        v-else
        :table-key="TABLE_KEYS.inspectionInterfaces"
        :data="interfaces"
        :loading="loading"
        size="small"
      >
        <DataColumn prop="host" label="主机" width="160" show-overflow-tooltip />
        <DataColumn prop="ifname" label="接口" width="150" show-overflow-tooltip />
        <DataColumn prop="in_bps_avg" label="入向日均" width="120">
          <template #default="{ row }">{{ fmtBps(row.in_bps_avg) }}</template>
        </DataColumn>
        <DataColumn prop="in_bps_max" label="入向峰值" width="120">
          <template #default="{ row }">{{ fmtBps(row.in_bps_max) }}</template>
        </DataColumn>
        <DataColumn prop="out_bps_avg" label="出向日均" width="120">
          <template #default="{ row }">{{ fmtBps(row.out_bps_avg) }}</template>
        </DataColumn>
        <DataColumn prop="out_bps_max" label="出向峰值" width="120">
          <template #default="{ row }">{{ fmtBps(row.out_bps_max) }}</template>
        </DataColumn>
        <DataColumn prop="in_usage_max" label="入向峰值率" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="usageTagType(row.in_usage_max)">{{ fmtPct(row.in_usage_max) }}</el-tag>
          </template>
        </DataColumn>
        <DataColumn prop="out_usage_max" label="出向峰值率" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="usageTagType(row.out_usage_max)">{{ fmtPct(row.out_usage_max) }}</el-tag>
          </template>
        </DataColumn>
        <DataColumn prop="date" label="业务日期" width="120" />
      </DataTable>
    </div>

    <DataPagination
      v-if="isDevice"
      v-model:page="devicePage"
      v-model:page-size="devicePageSize"
      :total="deviceTotal"
      @change="refetchDevices"
    />
    <DataPagination
      v-else
      v-model:page="interfacePage"
      v-model:page-size="interfacePageSize"
      :total="interfaceTotal"
      @change="refetchInterfaces"
    />
  </div>
</template>

<style scoped>
.results { display: flex; flex-direction: column; gap: 8px; }
.run-alert { margin-bottom: 2px; }
.stat-row { display: flex; gap: 12px; flex-wrap: wrap; }
.stat-row :deep(.stat-card) { flex: 1; min-width: 150px; }
.top-line { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: 12px; }
.top-label { color: var(--el-text-color-secondary); }
.table-box { background: var(--el-bg-color); border-radius: 8px; overflow: hidden; }
</style>
