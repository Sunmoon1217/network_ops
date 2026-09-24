<script setup lang="ts">
import { getParsers, getParserTemplates, getParserTemplate, updateParserTemplate } from '@/api/parsers'
import DataTable from '@/components/DataTable.vue'

import type { ParserItem, TemplateItem, TemplateRow } from '@/types'

const parsers = ref<ParserItem[]>([])
const templates = ref<TemplateItem[]>([])
const selectedTemplate = ref<TemplateRow | null>(null)
const templateContent = ref('')
const editContent = ref('')
const isEditing = ref(false)
const onlyUnlinked = ref(false)
const tableRef = ref()

/** 模板文件 + 引用它的解析器，按 configs → running 排序 */
const templateRows = computed<TemplateRow[]>(() => {
  const parsersByTemplate = new Map<string, ParserItem[]>()
  parsers.value.forEach((p) => {
    const list = parsersByTemplate.get(p.template_name) ?? []
    list.push(p)
    parsersByTemplate.set(p.template_name, list)
  })
  return [...templates.value]
    .sort((a, b) => a.group.localeCompare(b.group) || a.name.localeCompare(b.name))
    .map((t) => ({ ...t, parsers: parsersByTemplate.get(t.name) ?? [] }))
})

const visibleRows = computed(() =>
  onlyUnlinked.value ? templateRows.value.filter((r) => !r.parsers.length) : templateRows.value,
)

const linkedCount = computed(() => templateRows.value.filter((r) => r.parsers.length).length)

/** 合并「分组」列的单元格，让 configs / running 各占一段 */
const groupSpan = ({ row, column, rowIndex }: any) => {
  if (column.property !== 'group') return [1, 1]
  const rows = visibleRows.value
  if (rowIndex > 0 && rows[rowIndex - 1]?.group === row.group) return [0, 0]
  let span = 1
  for (let i = rowIndex + 1; i < rows.length && rows[i].group === row.group; i += 1) span += 1
  return [span, 1]
}

/** 数据重建后把选中态重新落到新行对象上，避免高亮丢失、右侧信息过期 */
watch(visibleRows, (rows) => {
  if (!selectedTemplate.value) return
  const current = rows.find((r) => r.name === selectedTemplate.value?.name)
  if (!current) return
  selectedTemplate.value = current
  nextTick(() => tableRef.value?.setCurrentRow(current))
})

const fetchParsers = async () => {
  try {
    const data = await getParsers()
    parsers.value = data.parsers || []
  } catch {
    ElMessage.error('获取解析器列表失败')
  }
}

const fetchTemplates = async () => {
  try {
    const data = await getParserTemplates()
    templates.value = data.templates || []
  } catch {
    ElMessage.error('获取模板列表失败')
  }
}

const handleRowClick = async (row: TemplateRow) => {
  selectedTemplate.value = row
  isEditing.value = false
  try {
    const data = await getParserTemplate(row.name)
    templateContent.value = data.content
    editContent.value = data.content
  } catch {
    ElMessage.error('获取模板内容失败')
  }
}

const saveTemplate = async () => {
  if (!selectedTemplate.value) return
  const name = selectedTemplate.value.name
  try {
    const res = await updateParserTemplate(name, editContent.value)
    templateContent.value = editContent.value
    isEditing.value = false
    const source = templates.value.find((t) => t.name === name)
    if (source && typeof res?.size === 'number') source.size = res.size
    ElMessage.success('保存成功')
  } catch {
    ElMessage.error('保存失败')
  }
}

const cancelEdit = () => {
  editContent.value = templateContent.value
  isEditing.value = false
}

const formatSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`
  return `${(bytes / 1024).toFixed(1)} KB`
}

onMounted(() => {
  fetchParsers()
  fetchTemplates()
})
</script>

<template>
  <div class="parsers-page">
    <div class="page-header">
      <h2>解析器模板管理</h2>
      <span class="muted">共 {{ templateRows.length }} 个模板，{{ linkedCount }} 个已关联解析器</span>
    </div>

    <div class="parsers-body">
      <!-- 左侧：模板文件（关联关系作为列呈现） -->
      <div class="parsers-sidebar">
        <div class="sidebar-bar">
          <span class="sidebar-title">模板文件</span>
          <el-checkbox v-model="onlyUnlinked" size="small">仅看未关联</el-checkbox>
        </div>
        <div class="table-wrap">
          <DataTable
            ref="tableRef"
            :data="visibleRows"
            size="small"
            highlight-current-row
            :span-method="groupSpan"
            @row-click="handleRowClick"
          >
            <el-table-column prop="group" label="分组" width="86" />
            <el-table-column prop="name" label="文件名" show-overflow-tooltip />
            <el-table-column label="关联解析器" width="190">
              <template #default="{ row }">
                <el-tooltip
                  v-for="p in row.parsers"
                  :key="`${p.vendor}/${p.device_type}`"
                  :content="p.description || p.class_name"
                  placement="top"
                >
                  <el-tag size="small" type="info" class="parser-tag">{{ p.vendor }}/{{ p.device_type }}</el-tag>
                </el-tooltip>
                <span v-if="!row.parsers.length" class="muted">未关联解析器</span>
              </template>
            </el-table-column>
          </DataTable>
        </div>
      </div>

      <!-- 右侧：模板预览/编辑 -->
      <div class="parsers-main">
        <div class="template-header">
          <div class="template-title">
            <span class="template-name">{{ selectedTemplate?.name || '请选择模板' }}</span>
            <template v-if="selectedTemplate">
              <span class="muted">{{ formatSize(selectedTemplate.size) }}</span>
              <el-tag
                v-for="p in selectedTemplate.parsers"
                :key="`${p.vendor}/${p.device_type}`"
                size="small"
                type="info"
              >
                {{ p.vendor }}/{{ p.device_type }}
              </el-tag>
            </template>
          </div>
          <div v-if="selectedTemplate" class="template-actions">
            <el-button v-if="!isEditing" size="small" @click="isEditing = true">编辑</el-button>
            <el-button v-if="isEditing" size="small" type="primary" @click="saveTemplate">保存</el-button>
            <el-button v-if="isEditing" size="small" @click="cancelEdit">取消</el-button>
          </div>
        </div>
        <div class="template-content">
          <el-input
            v-if="isEditing"
            v-model="editContent"
            type="textarea"
            :autosize="{ minRows: 20, maxRows: 40 }"
            style="font-family: monospace"
          />
          <pre v-else class="template-preview">{{ templateContent || '请选择模板查看内容' }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.parsers-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 20px;
}
.page-header {
  flex-shrink: 0;
  margin-bottom: 16px;
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.page-header h2 {
  margin: 0;
  font-size: 1.2rem;
  font-weight: 600;
}
.parsers-body {
  display: flex;
  gap: 16px;
  flex: 1;
  min-height: 0;
}
.parsers-sidebar {
  width: 460px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.sidebar-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  flex-shrink: 0;
}
.sidebar-title {
  font-size: 14px;
  font-weight: 600;
  color: #606266;
}
.table-wrap {
  flex: 1;
  min-height: 0;
}
.parser-tag + .parser-tag {
  margin-left: 4px;
}
.parsers-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.template-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  flex-shrink: 0;
  gap: 12px;
}
.template-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.template-name {
  font-size: 14px;
  font-weight: 600;
  color: #606266;
}
.template-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.template-content {
  flex: 1;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 16px;
  overflow: auto;
}
.template-preview {
  margin: 0;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
}
.muted {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
