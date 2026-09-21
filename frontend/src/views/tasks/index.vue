<script setup lang="ts">
import PageLayout from '@/layout/PageLayout.vue'
import DataTable from '@/components/DataTable.vue'
import DataPagination from '@/components/DataPagination.vue'
import { Refresh } from '@element-plus/icons-vue'
import { useCrudApi } from '@/composables/useCrudApi'
import {
  getTasks, getTask, createTask, cancelTask, getTaskDeviceOptions,
  type Task, type DeviceOption,
} from '@/api/tasks'

const { data: tasks, loading, search, page, pageSize, total, fetchData, refetch, pageParams } =
  useCrudApi<Task>()

const deviceOptions = ref<DeviceOption[]>([])
const filterDevice = ref<number | ''>('')
const filterStatus = ref<string>('')

// 设备筛选 / 状态筛选变化都要回到第一页（重新构造请求，首次 fetch 完成前也不会失效）
watch([filterDevice, filterStatus], () => {
  page.value = 1
  fetchAll()
})

const fetchAll = () =>
  fetchData(() =>
    getTasks(
      pageParams({
        device: filterDevice.value || undefined,
        status: filterStatus.value || undefined,
      })
    )
  )

const loadDeviceOptions = async () => {
  try {
    const res = await getTaskDeviceOptions()
    deviceOptions.value = res.data?.results ?? []
  } catch {
    ElMessage.error('设备列表加载失败')
  }
}

// 状态 / 类型的展示映射
const STATUS_LABELS: Record<string, string> = {
  pending: '等待中',
  running: '运行中',
  success: '成功',
  failed: '失败',
  cancelled: '已取消',
}
// 状态下拉选项（显式数组，避免直接在模板里遍历 Record 的键）
const STATUS_OPTIONS = [
  { value: 'pending', label: '等待中' },
  { value: 'running', label: '运行中' },
  { value: 'success', label: '成功' },
  { value: 'failed', label: '失败' },
  { value: 'cancelled', label: '已取消' },
]
const STATUS_TAGS: Record<string, string> = {
  pending: 'info',
  running: 'primary',
  success: 'success',
  failed: 'danger',
  cancelled: 'warning',
}
const TASK_TYPE_LABELS: Record<string, string> = {
  collect_config: '采集配置',
  backup_config: '备份配置',
  ansible_playbook: 'Ansible执行',
  batch_collect: '批量采集',
  config_backup: '配置备份',
}
const STAGE_TYPE_LABELS: Record<string, string> = {
  collection: '数据采集',
  parsing: '配置解析',
  storage: '数据存储',
}

const statusLabel = (status: string, fallback = '') => STATUS_LABELS[status] || fallback || status
const statusTag = (status: string) => STATUS_TAGS[status] || 'info'
const taskTypeLabel = (row: any) => TASK_TYPE_LABELS[row.task_type] || row.task_type_display || row.task_type
const stageTypeLabel = (row: any) => STAGE_TYPE_LABELS[row.stage_type] || row.stage_type_display || row.stage_type
const stageStatusLabel = (row: any) => statusLabel(row.status, row.status_display)
const stageStatusTag = (row: any) => statusTag(row.status)
const resultText = (result: any) => (result ? JSON.stringify(result, null, 2) : '')

// 自动刷新：列表里还有等待中 / 运行中的任务时每 5 秒拉一次
const hasActiveTask = computed(() =>
  (tasks.value as Task[]).some((item: Task) => item.status === 'pending' || item.status === 'running')
)
let pollTimer: ReturnType<typeof setInterval> | null = null
let polling = false
const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}
// 请求慢于轮询间隔时跳过本次，避免请求重叠
const poll = async () => {
  if (polling) return
  polling = true
  try {
    await refetch()
  } finally {
    polling = false
  }
}
watch(hasActiveTask, (active) => {
  stopPolling()
  if (active) {
    pollTimer = setInterval(() => {
      poll()
    }, 5000)
  }
})
onUnmounted(stopPolling)

// 新建任务
const createVisible = ref(false)
const submitting = ref(false)
const form = reactive({ device: undefined as number | undefined, task_type: 'collect_config' })

const openCreate = () => {
  form.device = undefined
  form.task_type = 'collect_config'
  createVisible.value = true
}

const submitCreate = async () => {
  if (!form.device) {
    ElMessage.warning('请选择设备')
    return
  }
  submitting.value = true
  try {
    await createTask({ device: form.device, task_type: form.task_type, params: {} })
    ElMessage.success('任务创建成功')
    createVisible.value = false
    await refetch()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '任务创建失败')
  } finally {
    submitting.value = false
  }
}

// 详情抽屉
const detailVisible = ref(false)
const detailLoading = ref(false)
const detailTask = ref<Task | null>(null)

const openDetail = async (id: number) => {
  detailVisible.value = true
  detailLoading.value = true
  detailTask.value = null
  try {
    const res = await getTask(id)
    detailTask.value = res.data
  } catch {
    ElMessage.error('任务详情加载失败')
    detailVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

// 取消任务（仅等待中 / 运行中可用）
const canCancel = (status: string) => status === 'pending' || status === 'running'
const handleCancel = async (id: number, hostname = '') => {
  const label = hostname ? `（${hostname}）` : ''
  try {
    await ElMessageBox.confirm(`确认取消任务 #${id}${label}？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await cancelTask(id)
    ElMessage.success('已取消')
    await refetch()
    // 抽屉正打开同一个任务时同步刷新详情
    if (detailVisible.value && detailTask.value?.id === id) {
      await openDetail(id)
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '取消失败')
  }
}

// 表格插槽给的 row 是 Element Plus 的 DefaultRow，只把 id 传进来再自行查找
const cancelRow = (id: number) => {
  const row = (tasks.value as Task[]).find((item: Task) => item.id === id)
  return handleCancel(id, row?.device_hostname)
}

onMounted(() => {
  loadDeviceOptions()
  fetchAll()
})
</script>

<template>
  <PageLayout title="任务中心">
    <template #actions>
      <el-select v-model="filterDevice" placeholder="设备" clearable style="width: 160px">
        <el-option v-for="d in deviceOptions" :key="d.id" :label="d.hostname" :value="d.id" />
      </el-select>
      <el-select v-model="filterStatus" placeholder="状态" clearable style="width: 130px">
        <el-option v-for="item in STATUS_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-input v-model="search" placeholder="搜索设备主机名" clearable style="width: 220px" />
      <el-button :icon="Refresh" @click="refetch()">刷新</el-button>
      <el-button type="primary" @click="openCreate">新建任务</el-button>
    </template>

    <div class="table-wrapper">
      <DataTable :data="tasks" :loading="loading">
        <el-table-column prop="device_hostname" label="设备" min-width="150" show-overflow-tooltip />
        <el-table-column label="类型" width="130">
          <template #default="{ row }">{{ taskTypeLabel(row) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status) as any" size="small">{{ statusLabel(row.status, row.status_display) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="180">
          <template #default="{ row }">
            <el-progress :percentage="row.progress" :stroke-width="10" />
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="完成时间" width="180">
          <template #default="{ row }">{{ row.completed_at || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right" align="center">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openDetail(row.id)">详情</el-button>
            <el-button
              size="small" link type="danger"
              :disabled="!canCancel(row.status)"
              @click="cancelRow(row.id)"
            >取消</el-button>
          </template>
        </el-table-column>
      </DataTable>
    </div>
    <DataPagination v-model:page="page" v-model:page-size="pageSize" :total="total" @change="refetch" />

    <el-dialog v-model="createVisible" title="新建任务" width="460px">
      <el-form label-width="80px">
        <el-form-item label="设备" required>
          <el-select v-model="form.device" placeholder="请选择设备" filterable style="width: 100%">
            <el-option v-for="d in deviceOptions" :key="d.id" :label="d.hostname" :value="d.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="任务类型">
          <el-select v-model="form.task_type" style="width: 100%">
            <el-option v-for="(label, key) in TASK_TYPE_LABELS" :key="key" :label="label" :value="key" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitCreate">提交</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="detailVisible" title="任务详情" size="60%">
      <div v-loading="detailLoading" class="detail">
        <template v-if="detailTask">
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="任务 ID">{{ detailTask.id }}</el-descriptions-item>
            <el-descriptions-item label="设备">{{ detailTask.device_hostname }}</el-descriptions-item>
            <el-descriptions-item label="类型">{{ taskTypeLabel(detailTask) }}</el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag :type="statusTag(detailTask.status) as any" size="small">
                {{ statusLabel(detailTask.status, detailTask.status_display) }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="进度">{{ detailTask.progress }}%</el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ detailTask.created_at }}</el-descriptions-item>
            <el-descriptions-item label="开始时间">{{ detailTask.started_at || '-' }}</el-descriptions-item>
            <el-descriptions-item label="完成时间">{{ detailTask.completed_at || '-' }}</el-descriptions-item>
          </el-descriptions>

          <div class="section-title">阶段列表</div>
          <div class="stage-wrapper">
            <DataTable :data="detailTask.stages || []">
              <el-table-column label="阶段" width="120">
                <template #default="{ row }">{{ stageTypeLabel(row) }}</template>
              </el-table-column>
              <el-table-column label="状态" width="100">
                <template #default="{ row }">
                  <el-tag :type="stageStatusTag(row) as any" size="small">{{ stageStatusLabel(row) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="started_at" label="开始时间" width="180" />
              <el-table-column prop="completed_at" label="结束时间" width="180" />
              <el-table-column prop="error_message" label="错误信息" min-width="160" show-overflow-tooltip />
            </DataTable>
          </div>

          <div class="section-title">结果</div>
          <pre class="result-block">{{ resultText(detailTask.result) || '暂无结果' }}</pre>

          <template v-if="detailTask.error_message">
            <div class="section-title">错误信息</div>
            <el-alert type="error" :closable="false" :title="detailTask.error_message" />
          </template>
        </template>
      </div>
    </el-drawer>
  </PageLayout>
</template>

<style scoped>
.table-wrapper { flex: 1; min-height: 0; background: #fff; border-radius: 8px; overflow: hidden; }
.detail { min-height: 120px; }
.section-title { margin: 16px 0 8px; font-size: 0.95rem; font-weight: 600; }
.stage-wrapper { height: 320px; background: #fff; border-radius: 8px; overflow: hidden; }
.result-block {
  margin: 0; padding: 10px; max-height: 220px; overflow: auto;
  background: var(--el-fill-color-light); border-radius: 6px;
  font-size: 12px; white-space: pre-wrap; word-break: break-all;
}
</style>
