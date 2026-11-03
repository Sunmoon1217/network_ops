<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Upload } from '@element-plus/icons-vue'
import { deleteSpreadsheet, exportSpreadsheet, getSpreadsheets, uploadSpreadsheet } from '@/api/spreadsheet'
import PageLayout from '@/layout/PageLayout.vue'
import DataTable from '@/components/DataTable.vue'
import DataColumn from '@/components/DataColumn.vue'
import { TABLE_KEYS } from '@/constants/tableKeys'
import type { SpreadsheetSummary } from '@/types'

// ---------------------------------------------------------------------------
// 电子表格·工作簿列表：上传 xlsx 建工作簿，进编辑页做表格展示 / 修改保存 /
// 导出 / 修改历史（历史在编辑页右侧抽屉）。
// ---------------------------------------------------------------------------

const router = useRouter()
const rows = ref<SpreadsheetSummary[]>([])
const loading = ref(false)
const uploading = ref(false)

const load = async () => {
  loading.value = true
  try {
    rows.value = (await getSpreadsheets()).data.results
  } catch {
    ElMessage.error('表格列表获取失败')
  } finally {
    loading.value = false
  }
}

/** 通用 Blob 下载（与导入模板下载同款写法） */
const saveAs = (data: Blob, filename: string) => {
  const url = URL.createObjectURL(data)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

/** 选中文件即上传（名称默认文件名），成功直接进编辑页 */
const onFileChange = async (uploadFile: { raw?: File }) => {
  const raw = uploadFile.raw
  if (!raw || uploading.value) return
  uploading.value = true
  try {
    const detail = (await uploadSpreadsheet(raw)).data
    ElMessage.success(`已导入「${detail.name}」`)
    await load()
    router.push({ name: 'docs-spreadsheet-edit', params: { id: detail.id } })
  } catch (e) {
    const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    ElMessage.error(detail ? `上传失败：${detail}` : '上传失败：仅支持 .xlsx 文件')
  } finally {
    uploading.value = false
  }
}

const onExport = async (rowId: number, rowName: string) => {
  try {
    const res = await exportSpreadsheet(rowId)
    saveAs(res.data as Blob, `${rowName}.xlsx`)
  } catch {
    ElMessage.error('导出失败，请稍后重试')
  }
}

const onDelete = async (rowId: number, rowName: string) => {
  try {
    await ElMessageBox.confirm(`确定删除「${rowName}」？修改历史将一并移除，此操作不可恢复。`, '删除确认', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await deleteSpreadsheet(rowId)
    ElMessage.success('已删除')
    await load()
  } catch {
    ElMessage.error('删除失败，请稍后重试')
  }
}

onMounted(load)
</script>

<template>
  <PageLayout title="电子表格">
    <template #actions>
      <el-upload :show-file-list="false" :auto-upload="false" accept=".xlsx" :on-change="onFileChange">
        <el-button type="primary" :loading="uploading">
          <el-icon><Upload /></el-icon>
          上传 xlsx
        </el-button>
      </el-upload>
    </template>

    <div class="table-wrapper">
      <DataTable :table-key="TABLE_KEYS.spreadsheetList" :data="rows" :loading="loading">
        <DataColumn prop="name" label="名称" :min-width="220">
          <template #default="{ row }">
            <el-button link type="primary" @click="router.push({ name: 'docs-spreadsheet-edit', params: { id: row.id } })">
              {{ row.name }}
            </el-button>
          </template>
        </DataColumn>
        <DataColumn prop="sheet_names" label="工作表" :min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ row.sheet_names.join('、') }}</template>
        </DataColumn>
        <DataColumn prop="latest_revision" label="版本" :width="80" align="center">
          <template #default="{ row }">
            <el-tag size="small" type="info">v{{ row.latest_revision }}</el-tag>
          </template>
        </DataColumn>
        <DataColumn prop="updated_by" label="最后修改" :min-width="110">
          <template #default="{ row }">{{ row.updated_by || '—' }}</template>
        </DataColumn>
        <DataColumn prop="updated_at" label="更新时间" :min-width="160">
          <template #default="{ row }">{{ new Date(row.updated_at).toLocaleString('zh-CN') }}</template>
        </DataColumn>
        <DataColumn prop="created_by" label="创建人" :min-width="110">
          <template #default="{ row }">{{ row.created_by || '—' }}</template>
        </DataColumn>
        <DataColumn prop="created_at" label="创建时间" :min-width="160">
          <template #default="{ row }">{{ new Date(row.created_at).toLocaleString('zh-CN') }}</template>
        </DataColumn>
        <DataColumn label="操作" :width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="router.push({ name: 'docs-spreadsheet-edit', params: { id: row.id } })">
              编辑
            </el-button>
            <el-button link type="primary" @click="onExport(row.id, row.name)">导出</el-button>
            <el-button link type="danger" @click="onDelete(row.id, row.name)">删除</el-button>
          </template>
        </DataColumn>
      </DataTable>
    </div>
  </PageLayout>
</template>

<style scoped>
.table-wrapper { flex: 1; min-height: 0; background: var(--el-bg-color); border-radius: 8px; overflow: hidden; }
</style>
