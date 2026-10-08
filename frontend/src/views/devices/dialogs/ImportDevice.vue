<script setup lang="ts">
import { importDevices } from '@/api/devices'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{
  'update:visible': [value: boolean]
  success: []
}>()

const importLoading = ref(false)
const selectedFile = ref<File | null>(null)
const importResult = ref<any>(null)

const handleImportChange = (uploadFile: any) => {
  if (!uploadFile.raw) return
  selectedFile.value = uploadFile.raw
}

const submitImport = async () => {
  if (!selectedFile.value) {
    ElMessage.warning('请先选择 Excel 文件')
    return
  }

  importLoading.value = true
  importResult.value = null
  ElMessage.info('正在上传并处理文件，请稍候...')

  try {
    const response = await importDevices(selectedFile.value)
    importResult.value = response.data
    if (response.data.success) {
      ElMessage.success('导入完成')
      emit('success')
    }
  } catch (e: any) {
    if (e.code === 'ECONNABORTED') {
      ElMessage.error('导入超时，请检查文件大小或稍后重试')
    } else {
      ElMessage.error(e.response?.data?.error || '导入失败')
    }
  } finally {
    importLoading.value = false
    selectedFile.value = null
  }
}

const handleClose = () => {
  importResult.value = null
  selectedFile.value = null
  emit('update:visible', false)
}
</script>

<template>
  <el-dialog
    :model-value="visible"
    title="导入设备"
    width="520px"
    @close="handleClose"
  >
    <div style="display: flex; flex-direction: column; gap: 12px">
      <el-upload
        :limit="1"
        accept=".xlsx,.xls"
        :disabled="importLoading"
        :auto-upload="false"
        :on-change="handleImportChange"
      >
        <el-button :loading="importLoading">
          {{ importLoading ? '处理中...' : '选择 Excel 文件' }}
        </el-button>
      </el-upload>

      <div style="color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.8">
        支持导入以下 Sheet（按顺序）：
        <strong>数据中心</strong>：名称 | 地址 | 联系人 | 电话 | 备注<br />
        <strong>机房</strong>：数据中心 | 机房名称 | 联系人 | 备注<br />
        <strong>机柜</strong>：数据中心 | 机房 | 机柜编号 | 排 | U数 | 功率 | 状态 | 备注<br />
        <strong>安全区</strong>：名称 | 颜色 | 描述<br />
         <strong>设备</strong>：主机名 | IP | 类型 | 厂商 | 型号 | 数据中心 | 机房 | 机柜 | 安全区 | U位 | 高度 | 备注 | 账号类型 | 用户名 | 密码 | Enable密码 | 端口 | 超时<br />
        <strong>配置文件</strong>：主机名 | 文件名(可选) | 配置目录(可选)
      </div>

      <el-button
        type="primary"
        :loading="importLoading"
        :disabled="!selectedFile || importLoading"
        @click="submitImport"
      >
        {{ importLoading ? '导入中...' : '确认导入' }}
      </el-button>

      <div v-if="importResult" style="margin-top: 8px">
        <div v-if="importResult.success" style="color: var(--el-color-success); font-weight: 600">导入完成</div>
        <div v-else style="color: var(--el-color-danger)">导入失败: {{ importResult.error }}</div>
        <div v-if="importResult.results" style="margin-top: 8px; font-size: 13px">
          <div v-for="(result, sheet) in importResult.results" :key="sheet" style="margin-bottom: 4px">
            <strong>{{ sheet }}</strong>：
            <span v-if="result.skipped" style="color: var(--el-text-color-secondary)">跳过（Sheet 不存在）</span>
            <span v-else-if="result.errors?.length" style="color: var(--el-color-danger)">
              {{ result.errors.length }} 条错误
            </span>
            <span v-else>新增 {{ result.created }}，更新 {{ result.updated }}</span>
          </div>
        </div>
      </div>
    </div>
  </el-dialog>
</template>
