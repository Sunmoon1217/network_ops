<script setup lang="ts">
import DataTable from '@/components/DataTable.vue'
import DataColumn from '@/components/DataColumn.vue'
import DataPagination from '@/components/DataPagination.vue'
import { TABLE_KEYS } from '@/constants/tableKeys'
import { useCrudApi } from '@/composables/useCrudApi'
import {
  getInspectionDevices,
  getInspectionInterfaces,
  getInspectionRuns,
  getInspectionSummary,
} from '@/api/inspection'

import type { InspectionDeviceMetric, InspectionDeviceSummary, InspectionInterfaceMetric, InspectionRun } from '@/types'

const props = defineProps<{
  kind: 'device' | 'line'
  date: string
  /** 是否展示顶部统计卡片（详情页隐藏，抽屉里显示） */
  showStats?: boolean
}>()

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
  pageParams: deviceParams,
} = useCrudApi<InspectionDeviceMetric>()

const {
  data: interfaces,
  loading: interfacesLoading,
  page: interfacePage,
  pageSize: interfacePageSize,
  total: interfaceTotal,
  fetchData: fetchInterfaces,
  refetch: refetchInterfaces,
  pageParams: interfaceParams,
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
    await fetchDevices(() => getInspectionDevices(deviceParams({ date: props.date })))
  } else {
    interfacePage.value = 1
    await fetchInterfaces(() => getInspectionInterfaces(interfaceParams({ date: props.date })))
  }
}

watch(() => [props.kind, props.date], load)
onMounted(load)

const fmtPct = (value: number | null) => (value == null ? '—' : `${value}%`)
const fmtBps = (value: number | null) => {
  if (value == null) return '—'
  const units = [
    { size: 1e9, label: 'Gbps' },
    { size: 1e6, label: 'Mbps' },
    { size: 1e3, label: 'Kbps' },
  ]
  const hit = units.find((u) => value >= u.size)
  return hit ? `${(value / hit.size).toFixed(2)} ${hit.label}` : `${value.toFixed(0)} bps`
}
const usageTagType = (value: number | null) => {
  if (value == null) return 'info'
  if (value >= 80) return 'danger'
  if (value >= 60) return 'warning'
  return 'success'
}
const fmtTime = (value: string | null) => (value ? value.replace('T', ' ').slice(0, 19) : '—')

const statusTag = computed((): { type: 'success' | 'danger' | 'info'; text: string } => {
  if (run.value) {
    return { type: run.value.status === 'success' ? 'success' : 'danger', text: run.value.status === 'success' ? '成功' : '失败' }
  }
  return { type: 'info', text: '未执行' }
})

const statItems = computed((): { label: string; value: string; tagType?: 'success' | 'danger' | 'info' }[] => {
  if (isDevice.value) {
    return [
      { label: '巡检状态', value: statusTag.value.text, tagType: statusTag.value.type },
      { label: '设备数', value: String(summary.value?.device_count ?? 0) },
      { label: 'CPU 日均', value: fmtPct(summary.value?.cpu_avg ?? null) },
      { label: '内存日均', value: fmtPct(summary.value?.memory_avg ?? null) },
    ]
  }
  return [
    { label: '巡检状态', value: statusTag.value.text, tagType: statusTag.value.type },
    { label: '专线接口数', value: String(interfaceTotal.value) },
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

    <div v-if="showStats !== false" class="stat-row">
      <div v-for="item in statItems" :key="item.label" class="stat-card">
        <div class="stat-label">{{ item.label }}</div>
        <div class="stat-value">
          <el-tag v-if="item.tagType" :type="item.tagType" size="default">{{ item.value }}</el-tag>
          <span v-else>{{ item.value }}</span>
        </div>
      </div>
    </div>

    <div v-if="showStats !== false && isDevice && summary?.cpu_top.length" class="top-line">
      <span class="top-label">CPU 峰值 TOP5：</span>
      <el-tag v-for="row in summary.cpu_top" :key="row.name" size="small" :type="usageTagType(row.cpu_max)">
        {{ row.name }} {{ fmtPct(row.cpu_max) }}
      </el-tag>
    </div>

    <div class="table-wrap">
      <DataTable
        v-if="isDevice"
        :table-key="TABLE_KEYS.inspectionDevices"
        :data="devices"
        :loading="loading"
        height="100%"
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
        height="100%"
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

    <div class="pagination-wrap">
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
  </div>
</template>

<style scoped>
.results { display: flex; flex-direction: column; min-height: 0; gap: 10px; flex: 1; }
.run-alert { margin-top: 2px; }

.stat-row { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; flex-shrink: 0; }
.stat-card { background: var(--el-bg-color); border: 1px solid var(--el-border-color-lighter); border-radius: 8px; padding: 12px 14px; min-width: 0; }
.stat-label { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.stat-value { font-size: 18px; font-weight: 600; color: var(--el-text-color-primary); display: flex; align-items: center; }

.top-line { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: 12px; flex-shrink: 0; }
.top-label { color: var(--el-text-color-secondary); }

.table-wrap { flex: 1; min-height: 0; background: var(--el-bg-color); border-radius: 8px; overflow: hidden; }
.pagination-wrap { flex-shrink: 0; }

@media (max-width: 900px) {
  .stat-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
