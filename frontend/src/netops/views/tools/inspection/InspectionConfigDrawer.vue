<script setup lang="ts">
import DataTable from '@/components/DataTable.vue'
import DataColumn from '@/components/DataColumn.vue'
import DataPagination from '@/components/DataPagination.vue'
import { TABLE_KEYS } from '@/constants/tableKeys'
import { useAuthStore } from '@netops/stores/auth'
import {
  createInspectionDeviceTarget,
  createInspectionTarget,
  deleteInspectionDeviceTarget,
  deleteInspectionTarget,
  getInspectionConfig,
  getInspectionDeviceTargets,
  getInspectionTargets,
  updateInspectionConfig,
  updateInspectionDeviceTarget,
  updateInspectionTarget,
} from '@/api/inspection'

import type { InspectionConfig } from '@/types'

const props = defineProps<{
  modelValue: boolean
  kind: 'device' | 'line'
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: []
}>()

const authStore = useAuthStore()
const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})
const isDevice = computed(() => props.kind === 'device')

// ———————————————————— 调度配置 ————————————————————
const configLoading = ref(false)
const saving = ref(false)
const config = ref<InspectionConfig | null>(null)
const scheduleTime = ref('06:00')
const windowStart = ref('00:00')
const windowEnd = ref('06:00')
const pad = (value: number) => String(value).padStart(2, '0')

const loadConfig = async () => {
  configLoading.value = true
  try {
    const data = (await getInspectionConfig()).data
    config.value = data
    scheduleTime.value = `${pad(data.schedule_hour)}:${pad(data.schedule_minute)}`
    windowStart.value = data.window_start.slice(0, 5)
    windowEnd.value = data.window_end.slice(0, 5)
  } catch {
    ElMessage.error('加载巡检配置失败')
  } finally {
    configLoading.value = false
  }
}

const saveSchedule = async () => {
  if (windowStart.value >= windowEnd.value) {
    ElMessage.warning('巡检时间范围的结束必须晚于开始')
    return
  }
  const [hour, minute] = scheduleTime.value.split(':').map(Number)
  saving.value = true
  try {
    config.value = (
      await updateInspectionConfig({
        schedule_hour: hour,
        schedule_minute: minute,
        window_start: `${windowStart.value}:00`,
        window_end: `${windowEnd.value}:00`,
      })
    ).data
    ElMessage.success('巡检调度已保存')
    emit('saved')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.response?.data?.non_field_errors?.[0] || '保存失败')
  } finally {
    saving.value = false
  }
}

// ———————————————————— 巡检对象 ————————————————————
const targetSearch = ref('')
const targets = ref<any[]>([])
const targetLoading = ref(false)
const targetPage = ref(1)
const targetPageSize = ref(20)
const targetTotal = ref(0)

const loadTargets = async () => {
  targetLoading.value = true
  try {
    const params = { search: targetSearch.value || undefined, page: targetPage.value, page_size: targetPageSize.value }
    const response = isDevice.value
      ? await getInspectionDeviceTargets(params)
      : await getInspectionTargets(params)
    targets.value = response.data.results
    targetTotal.value = response.data.count
  } catch {
    targets.value = []
    targetTotal.value = 0
  } finally {
    targetLoading.value = false
  }
}

let searchTimer: ReturnType<typeof setTimeout> | null = null
watch(targetSearch, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    targetPage.value = 1
    loadTargets()
  }, 300)
})
watch(targetPage, loadTargets)
watch(targetPageSize, () => {
  targetPage.value = 1
  loadTargets()
})
onUnmounted(() => {
  if (searchTimer) clearTimeout(searchTimer)
})

// 新增 / 编辑巡检对象
const targetDialog = ref(false)
const targetSubmitting = ref(false)
const targetFormRef = ref()
const editingTargetId = ref(0)
const targetForm = reactive({ host: '', ifname: '', itemidsText: '', enabled: true })
const targetDialogTitle = computed(() => {
  const name = isDevice.value ? '设备巡检对象' : '专线巡检对象'
  return editingTargetId.value ? `编辑${name}` : `新增${name}`
})
const targetRules = computed(() =>
  isDevice.value
    ? { host: [{ required: true, message: '请输入 Zabbix 主机名', trigger: 'blur' }] }
    : {
        host: [{ required: true, message: '请输入 Zabbix 主机名', trigger: 'blur' }],
        ifname: [{ required: true, message: '请输入接口名', trigger: 'blur' }],
      },
)

const openTargetCreate = () => {
  editingTargetId.value = 0
  targetForm.host = ''
  targetForm.ifname = ''
  targetForm.itemidsText = ''
  targetForm.enabled = true
  targetDialog.value = true
  nextTick(() => targetFormRef.value?.clearValidate())
}

const openTargetEdit = (row: any) => {
  editingTargetId.value = row.id
  targetForm.host = row.host
  targetForm.ifname = row.ifname ?? ''
  targetForm.itemidsText = (row.itemids ?? []).join(', ')
  targetForm.enabled = row.enabled
  targetDialog.value = true
  nextTick(() => targetFormRef.value?.clearValidate())
}

const submitTarget = async () => {
  try {
    await targetFormRef.value?.validate()
  } catch {
    return
  }
  targetSubmitting.value = true
  try {
    if (isDevice.value) {
      const payload = { host: targetForm.host.trim(), enabled: targetForm.enabled }
      if (editingTargetId.value) {
        await updateInspectionDeviceTarget(editingTargetId.value, payload)
      } else {
        await createInspectionDeviceTarget(payload)
      }
    } else {
      const payload = {
        host: targetForm.host.trim(),
        ifname: targetForm.ifname.trim(),
        itemids: targetForm.itemidsText.split(/[\s,，]+/).filter(Boolean),
        enabled: targetForm.enabled,
      }
      if (editingTargetId.value) {
        await updateInspectionTarget(editingTargetId.value, payload)
      } else {
        await createInspectionTarget(payload)
      }
    }
    ElMessage.success('已保存')
    targetDialog.value = false
    loadTargets()
  } catch (e: any) {
    const data = e?.response?.data
    ElMessage.error(data?.non_field_errors?.[0] || data?.detail || '保存失败')
  } finally {
    targetSubmitting.value = false
  }
}

const toggleTarget = async (row: any) => {
  try {
    if (isDevice.value) {
      await updateInspectionDeviceTarget(row.id, { enabled: row.enabled })
    } else {
      await updateInspectionTarget(row.id, { enabled: row.enabled })
    }
  } catch {
    row.enabled = !row.enabled
    ElMessage.error('切换启用状态失败')
  }
}

const removeTarget = async (row: any) => {
  const label = isDevice.value ? row.host : `${row.host}@${row.ifname}`
  try {
    await ElMessageBox.confirm(`确认删除巡检对象 ${label}？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    if (isDevice.value) {
      await deleteInspectionDeviceTarget(row.id)
    } else {
      await deleteInspectionTarget(row.id)
    }
    ElMessage.success('已删除')
    loadTargets()
  } catch {
    ElMessage.error('删除失败')
  }
}

const fmtTime = (value: string | null) => (value ? value.replace('T', ' ').slice(0, 19) : '—')

watch(visible, (open) => {
  if (!open) return
  loadConfig()
  targetSearch.value = ''
  targetPage.value = 1
  loadTargets()
})
watch(isDevice, () => {
  if (!visible.value) return
  targetSearch.value = ''
  targetPage.value = 1
  loadTargets()
})
</script>

<template>
  <el-drawer v-model="visible" :title="isDevice ? '设备巡检配置' : '专线巡检配置'" size="760px">
    <div v-loading="configLoading" class="section">
      <h4 class="section-title">巡检调度</h4>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="时间设置对设备巡检与专线巡检共同生效"
        description="每到一个巡检时间点，采集当天「巡检时间范围」内的数据；修改后当日未执行前立即生效。"
        class="section-tip"
      />
      <el-form label-width="110px" class="schedule-form">
        <el-form-item label="巡检时间点">
          <el-time-picker
            v-model="scheduleTime"
            format="HH:mm"
            value-format="HH:mm"
            :clearable="false"
            style="width: 160px"
          />
        </el-form-item>
        <el-form-item label="巡检时间范围">
          <div class="range-row">
            <el-time-picker v-model="windowStart" format="HH:mm" value-format="HH:mm" :clearable="false" style="width: 140px" />
            <span class="range-sep">至</span>
            <el-time-picker v-model="windowEnd" format="HH:mm" value-format="HH:mm" :clearable="false" style="width: 140px" />
          </div>
        </el-form-item>
        <el-form-item v-if="scheduleTime < windowEnd" label=" ">
          <el-alert
            type="warning"
            :closable="false"
            show-icon
            title="巡检时间点早于时间范围结束，当天只能采到巡检时刻之前的数据"
          />
        </el-form-item>
        <el-form-item v-if="config?.last_dispatch_date" label="最近投递">
          <span class="muted">{{ config.last_dispatch_date }}</span>
        </el-form-item>
        <el-form-item v-if="authStore.canWrite">
          <el-button type="primary" :loading="saving" @click="saveSchedule">保存调度</el-button>
        </el-form-item>
      </el-form>
    </div>

    <div class="section">
      <div class="section-head">
        <h4 class="section-title">巡检对象</h4>
        <div class="section-actions">
          <el-input
            v-model="targetSearch"
            :placeholder="isDevice ? '搜索主机名' : '搜索主机名 / 接口名'"
            clearable
            style="width: 180px"
            size="small"
          />
          <el-button v-if="authStore.canWrite" type="primary" size="small" @click="openTargetCreate">新增对象</el-button>
        </div>
      </div>
      <div class="target-table">
        <DataTable
          v-if="isDevice"
          :table-key="TABLE_KEYS.inspectionDeviceTargets"
          :data="targets"
          :loading="targetLoading"
          size="small"
        >
          <DataColumn prop="host" label="Zabbix 主机名" min-width="220" show-overflow-tooltip />
          <DataColumn prop="enabled" label="启用" width="80" align="center">
            <template #default="{ row }">
              <el-switch v-if="authStore.canWrite" v-model="row.enabled" size="small" @change="toggleTarget(row)" />
              <el-tag v-else :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? '是' : '否' }}</el-tag>
            </template>
          </DataColumn>
          <DataColumn prop="updated_at" label="更新时间" width="170">
            <template #default="{ row }">{{ fmtTime(row.updated_at) }}</template>
          </DataColumn>
          <DataColumn v-if="authStore.canWrite" label="操作" width="110" align="center">
            <template #default="{ row }">
              <el-button size="small" link type="primary" @click="openTargetEdit(row)">编辑</el-button>
              <el-button size="small" link type="danger" @click="removeTarget(row)">删除</el-button>
            </template>
          </DataColumn>
        </DataTable>

        <DataTable
          v-else
          :table-key="TABLE_KEYS.inspectionTargets"
          :data="targets"
          :loading="targetLoading"
          size="small"
        >
          <DataColumn prop="host" label="Zabbix 主机名" min-width="170" show-overflow-tooltip />
          <DataColumn prop="ifname" label="接口名" min-width="130" show-overflow-tooltip />
          <DataColumn prop="itemids" label="监控项 ID" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.itemids.length" class="mono">{{ row.itemids.join(', ') }}</span>
              <el-tag v-else size="small" type="info">按名称自动搜索</el-tag>
            </template>
          </DataColumn>
          <DataColumn prop="enabled" label="启用" width="80" align="center">
            <template #default="{ row }">
              <el-switch v-if="authStore.canWrite" v-model="row.enabled" size="small" @change="toggleTarget(row)" />
              <el-tag v-else :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? '是' : '否' }}</el-tag>
            </template>
          </DataColumn>
          <DataColumn prop="updated_at" label="更新时间" width="170">
            <template #default="{ row }">{{ fmtTime(row.updated_at) }}</template>
          </DataColumn>
          <DataColumn v-if="authStore.canWrite" label="操作" width="110" align="center">
            <template #default="{ row }">
              <el-button size="small" link type="primary" @click="openTargetEdit(row)">编辑</el-button>
              <el-button size="small" link type="danger" @click="removeTarget(row)">删除</el-button>
            </template>
          </DataColumn>
        </DataTable>
      </div>
      <DataPagination v-model:page="targetPage" v-model:page-size="targetPageSize" :total="targetTotal" @change="loadTargets" />
    </div>

    <el-dialog v-model="targetDialog" :title="targetDialogTitle" width="480px" append-to-body>
      <el-form ref="targetFormRef" :model="targetForm" :rules="targetRules" label-width="110px">
        <el-form-item label="Zabbix 主机名" prop="host">
          <el-input v-model="targetForm.host" placeholder="与 Zabbix 主机显示名一致" />
        </el-form-item>
        <el-form-item v-if="!isDevice" label="接口名" prop="ifname">
          <el-input v-model="targetForm.ifname" placeholder="如 GE1/0/1" />
        </el-form-item>
        <el-form-item v-if="!isDevice" label="监控项 ID">
          <el-input
            v-model="targetForm.itemidsText"
            type="textarea"
            :rows="2"
            placeholder="可留空；留空时按主机名 + 接口名自动搜索带宽监控项"
          />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="targetForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="targetDialog = false">取消</el-button>
        <el-button type="primary" :loading="targetSubmitting" @click="submitTarget">保存</el-button>
      </template>
    </el-dialog>
  </el-drawer>
</template>

<style scoped>
.section + .section { margin-top: 18px; }
.section-title { margin: 0 0 8px; font-size: 14px; color: var(--el-text-color-primary); }
.section-tip { margin-bottom: 12px; }
.schedule-form { max-width: 420px; }
.range-row { display: flex; align-items: center; gap: 8px; }
.range-sep { color: var(--el-text-color-secondary); font-size: 12px; }
.muted { color: var(--el-text-color-secondary); font-size: 12px; }
.section-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.section-actions { display: flex; align-items: center; gap: 8px; }
.target-table { height: 360px; background: var(--el-bg-color); border-radius: 8px; overflow: hidden; }
.mono { font-family: Menlo, Consolas, monospace; font-size: 12px; }
</style>
