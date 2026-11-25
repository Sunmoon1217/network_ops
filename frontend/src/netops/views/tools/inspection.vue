<script setup lang="ts">
import PageLayout from '@/components/PageLayout.vue'
import DataTable from '@/components/DataTable.vue'
import DataColumn from '@/components/DataColumn.vue'
import DataPagination from '@/components/DataPagination.vue'
import StatCard from '@/components/StatCard.vue'
import { TABLE_KEYS } from '@/constants/tableKeys'
import { useCrudApi } from '@/composables/useCrudApi'
import { useAuthStore } from '@netops/stores/auth'
import {
  createInspectionTarget,
  deleteInspectionTarget,
  getInspectionDevices,
  getInspectionInterfaces,
  getInspectionRuns,
  getInspectionSummary,
  getInspectionTargets,
  updateInspectionTarget,
} from '@/api/inspection'

import type { InspectionDeviceMetric, InspectionDeviceSummary, InspectionInterfaceMetric, InspectionRun, InspectionTarget } from '@/types'

const authStore = useAuthStore()
const activeTab = ref<'results' | 'targets'>('results')

// ———————————————————— 巡检结果 ————————————————————
const filterDate = ref('')
const hostKeyword = ref('')
const summary = ref<InspectionDeviceSummary | null>(null)
const summaryLoading = ref(false)
const runs = ref<InspectionRun[]>([])
const runsLoading = ref(false)

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

/** 日期 / 主机筛选：交给后端，空值不传 */
const resultParams = () => ({
  date: filterDate.value || undefined,
  host: hostKeyword.value || undefined,
})

const loadSummary = async () => {
  summaryLoading.value = true
  try {
    summary.value = (await getInspectionSummary(resultParams())).data
  } catch {
    summary.value = null
  } finally {
    summaryLoading.value = false
  }
}

const loadRuns = async () => {
  runsLoading.value = true
  try {
    runs.value = (await getInspectionRuns({ page_size: 5 })).data.results
  } catch {
    runs.value = []
  } finally {
    runsLoading.value = false
  }
}

const loadResults = async () => {
  devicePage.value = 1
  interfacePage.value = 1
  await Promise.all([
    loadSummary(),
    loadRuns(),
    fetchDevices(() => getInspectionDevices(deviceParams(resultParams()))),
    fetchInterfaces(() => getInspectionInterfaces(interfaceParams(resultParams()))),
  ])
}

let hostTimer: ReturnType<typeof setTimeout> | null = null
watch(hostKeyword, () => {
  if (hostTimer) clearTimeout(hostTimer)
  hostTimer = setTimeout(loadResults, 300)
})
watch(filterDate, loadResults)
onUnmounted(() => {
  if (hostTimer) clearTimeout(hostTimer)
})

// ———————————————————— 采集对象 ————————————————————
const {
  data: targets,
  loading: targetsLoading,
  search: targetSearch,
  page: targetPage,
  pageSize: targetPageSize,
  total: targetTotal,
  fetchData: fetchTargets,
  refetch: refetchTargets,
  pageParams: targetParams,
} = useCrudApi<InspectionTarget>()

const loadTargets = () => fetchTargets(() => getInspectionTargets(targetParams()))

const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref()
const form = reactive({ id: 0, host: '', ifname: '', itemidsText: '', enabled: true })
const editing = computed(() => form.id > 0)
const formRules = {
  host: [{ required: true, message: '请输入 Zabbix 主机名', trigger: 'blur' }],
  ifname: [{ required: true, message: '请输入接口名', trigger: 'blur' }],
}

const openCreate = () => {
  form.id = 0
  form.host = ''
  form.ifname = ''
  form.itemidsText = ''
  form.enabled = true
  dialogVisible.value = true
}

const openEdit = (row: any) => {
  form.id = row.id
  form.host = row.host
  form.ifname = row.ifname
  form.itemidsText = row.itemids.join(', ')
  form.enabled = row.enabled
  dialogVisible.value = true
}

const submitTarget = async () => {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  const payload = {
    host: form.host.trim(),
    ifname: form.ifname.trim(),
    itemids: form.itemidsText.split(/[\s,，]+/).filter(Boolean),
    enabled: form.enabled,
  }
  submitting.value = true
  try {
    if (editing.value) {
      await updateInspectionTarget(form.id, payload)
    } else {
      await createInspectionTarget(payload)
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    refetchTargets()
  } catch (e: any) {
    const data = e?.response?.data
    ElMessage.error(data?.non_field_errors?.[0] || data?.detail || '保存失败')
  } finally {
    submitting.value = false
  }
}

const toggleTarget = async (row: any) => {
  try {
    await updateInspectionTarget(row.id, { enabled: row.enabled })
  } catch {
    row.enabled = !row.enabled
    ElMessage.error('切换启用状态失败')
  }
}

const removeTarget = async (row: any) => {
  try {
    await ElMessageBox.confirm(`确认删除采集目标 ${row.host}@${row.ifname}？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteInspectionTarget(row.id)
    ElMessage.success('已删除')
    refetchTargets()
  } catch {
    ElMessage.error('删除失败')
  }
}

// ———————————————————— 展示辅助 ————————————————————
const summaryCards = computed(() => {
  const data = summary.value
  return [
    { label: '统计日期', value: data?.date ?? '暂无数据' },
    { label: '设备数', value: data?.device_count ?? 0 },
    { label: 'CPU 日均', value: data?.cpu_avg == null ? '—' : `${data.cpu_avg}%` },
    { label: '内存日均', value: data?.memory_avg == null ? '—' : `${data.memory_avg}%` },
  ]
})

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

onMounted(() => {
  loadResults()
  loadTargets()
})
</script>

<template>
  <PageLayout title="巡检项目">
    <el-tabs v-model="activeTab" class="page-tabs">
      <!-- ───────────────────── 巡检结果 ───────────────────── -->
      <el-tab-pane label="巡检结果" name="results">
        <div class="tab-body">
          <div class="toolbar">
            <el-date-picker
              v-model="filterDate"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="日期（默认最新）"
              clearable
              style="width: 180px"
            />
            <el-input v-model="hostKeyword" placeholder="搜索主机名" clearable style="width: 200px" />
            <el-button :loading="summaryLoading || devicesLoading || interfacesLoading" @click="loadResults">刷新</el-button>
            <span class="hint">数据由每日巡检任务写入；日期留空时取最新有数据的一天</span>
          </div>

          <div class="stat-row">
            <StatCard v-for="card in summaryCards" :key="card.label" :label="card.label" :value="card.value" />
          </div>

          <div v-if="summary?.cpu_top.length" class="top-line">
            <span class="top-label">CPU 峰值 TOP5：</span>
            <el-tag v-for="row in summary.cpu_top" :key="row.name" size="small" :type="usageTagType(row.cpu_max)">
              {{ row.name }} {{ fmtPct(row.cpu_max) }}
            </el-tag>
          </div>

          <h4 class="section-title">巡检批次<span class="muted">最近 5 次</span></h4>
          <div class="runs-box">
            <DataTable :table-key="TABLE_KEYS.inspectionRuns" :data="runs" :loading="runsLoading" size="small">
              <DataColumn prop="date" label="业务日期" width="120" />
              <DataColumn prop="status" label="结果" width="90">
                <template #default="{ row }">
                  <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
                    {{ row.status === 'success' ? '成功' : '失败' }}
                  </el-tag>
                </template>
              </DataColumn>
              <DataColumn prop="device_count" label="设备条数" width="100" />
              <DataColumn prop="interface_count" label="接口条数" width="100" />
              <DataColumn prop="finished_at" label="完成时间" width="170">
                <template #default="{ row }">{{ fmtTime(row.finished_at) }}</template>
              </DataColumn>
              <DataColumn prop="error" label="错误信息" min-width="220" show-overflow-tooltip>
                <template #default="{ row }">{{ row.error || '—' }}</template>
              </DataColumn>
            </DataTable>
          </div>

          <h4 class="section-title">设备 CPU / 内存<span class="muted">共 {{ deviceTotal }} 条</span></h4>
          <div class="table-box">
            <DataTable :table-key="TABLE_KEYS.inspectionDevices" :data="devices" :loading="devicesLoading" size="small">
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
          </div>
          <DataPagination v-model:page="devicePage" v-model:page-size="devicePageSize" :total="deviceTotal" @change="refetchDevices" />

          <h4 class="section-title">接口带宽<span class="muted">共 {{ interfaceTotal }} 条</span></h4>
          <div class="table-box">
            <DataTable :table-key="TABLE_KEYS.inspectionInterfaces" :data="interfaces" :loading="interfacesLoading" size="small">
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
          <DataPagination v-model:page="interfacePage" v-model:page-size="interfacePageSize" :total="interfaceTotal" @change="refetchInterfaces" />
        </div>
      </el-tab-pane>

      <!-- ───────────────────── 采集对象 ───────────────────── -->
      <el-tab-pane label="采集对象" name="targets">
        <div class="tab-body">
          <div class="toolbar">
            <el-button v-if="authStore.canWrite" type="primary" @click="openCreate">新增采集对象</el-button>
            <el-input v-model="targetSearch" placeholder="搜索主机名 / 接口名" clearable style="width: 220px" />
            <span class="hint">采集对象 = Zabbix 主机 + 接口；启用的对象参与每日接口带宽巡检</span>
          </div>

          <div class="table-box tall">
            <DataTable :table-key="TABLE_KEYS.inspectionTargets" :data="targets" :loading="targetsLoading">
              <DataColumn prop="host" label="Zabbix 主机名" min-width="200" show-overflow-tooltip />
              <DataColumn prop="ifname" label="接口名" min-width="160" show-overflow-tooltip />
              <DataColumn prop="itemids" label="监控项 ID" min-width="200" show-overflow-tooltip>
                <template #default="{ row }">
                  <span v-if="row.itemids.length" class="mono">{{ row.itemids.join(', ') }}</span>
                  <el-tag v-else size="small" type="info">按名称自动搜索</el-tag>
                </template>
              </DataColumn>
              <DataColumn prop="enabled" label="启用" width="90" align="center">
                <template #default="{ row }">
                  <el-switch
                    v-if="authStore.canWrite"
                    v-model="row.enabled"
                    size="small"
                    @change="toggleTarget(row)"
                  />
                  <el-tag v-else :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? '是' : '否' }}</el-tag>
                </template>
              </DataColumn>
              <DataColumn prop="updated_at" label="更新时间" width="170">
                <template #default="{ row }">{{ fmtTime(row.updated_at) }}</template>
              </DataColumn>
              <DataColumn v-if="authStore.canWrite" label="操作" width="120" fixed="right" align="center">
                <template #default="{ row }">
                  <el-button size="small" link type="primary" @click="openEdit(row)">编辑</el-button>
                  <el-button size="small" link type="danger" @click="removeTarget(row)">删除</el-button>
                </template>
              </DataColumn>
            </DataTable>
          </div>
          <DataPagination v-model:page="targetPage" v-model:page-size="targetPageSize" :total="targetTotal" @change="refetchTargets" />
        </div>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑采集对象' : '新增采集对象'" width="480px">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="110px">
        <el-form-item label="Zabbix 主机名" prop="host">
          <el-input v-model="form.host" placeholder="与 Zabbix 主机显示名一致" />
        </el-form-item>
        <el-form-item label="接口名" prop="ifname">
          <el-input v-model="form.ifname" placeholder="如 GE1/0/1" />
        </el-form-item>
        <el-form-item label="监控项 ID">
          <el-input
            v-model="form.itemidsText"
            type="textarea"
            :rows="2"
            placeholder="可留空；留空时按主机名 + 接口名自动搜索带宽监控项"
          />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitTarget">保存</el-button>
      </template>
    </el-dialog>
  </PageLayout>
</template>

<style scoped>
.page-tabs { flex: 1; min-height: 0; }
.tab-body { display: flex; flex-direction: column; gap: 8px; }

.toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 4px; }
.hint { font-size: 12px; color: var(--el-text-color-secondary); }

.stat-row { display: flex; gap: 12px; flex-wrap: wrap; }
.stat-row :deep(.stat-card) { flex: 1; min-width: 160px; }

.top-line { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: 12px; }
.top-label { color: var(--el-text-color-secondary); }

.section-title { display: flex; align-items: center; gap: 8px; margin: 12px 0 6px; font-size: 14px; color: var(--el-text-color-primary); }
.muted { font-size: 12px; font-weight: 400; color: var(--el-text-color-secondary); }

.runs-box { height: 200px; background: var(--el-bg-color); border-radius: 8px; overflow: hidden; }
.table-box { height: 320px; background: var(--el-bg-color); border-radius: 8px; overflow: hidden; }
.table-box.tall { height: calc(100vh - 280px); min-height: 320px; }

.mono { font-family: Menlo, Consolas, monospace; font-size: 12px; }
</style>
