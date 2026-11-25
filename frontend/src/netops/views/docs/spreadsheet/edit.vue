<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import {
  exportSpreadsheet,
  getSpreadsheet,
  getSpreadsheetRevision,
  getSpreadsheetRevisions,
  restoreSpreadsheetRevision,
  saveSpreadsheet,
} from '@/api/spreadsheet'
import PageLayout from '@/components/PageLayout.vue'
import DataTable from '@/components/DataTable.vue'
import DataColumn from '@/components/DataColumn.vue'
import { TABLE_KEYS } from '@/constants/tableKeys'
import type {
  SheetChangeSummary,
  SheetCellValue,
  SpreadsheetData,
  SpreadsheetRevision,
  SpreadsheetRevisionDetail,
} from '@/types'

// ---------------------------------------------------------------------------
// 电子表格·工作簿编辑页：每个工作表一张网格，rows 的前 header_rows 行是表头
// （多行表头），双击单元格编辑、增删行；保存走后端 diff 落「全量快照 + 单元格级
// 变更」的新版本，右侧抽屉是修改历史（查看差异 / 导出历史版本 / 回滚）。
// ---------------------------------------------------------------------------

const route = useRoute()
const router = useRouter()
const bookId = computed(() => Number(route.params.id))

const name = ref('')
const latestRevision = ref(0)
const book = ref<SpreadsheetData | null>(null)
const saved = ref<SpreadsheetData | null>(null)
const dirty = ref(false)
const loading = ref(false)
const activeName = ref('')

const activeIdx = computed(() => book.value?.sheets.findIndex((s) => s.name === activeName.value) ?? -1)
const sheetRows = computed(() => (activeIdx.value >= 0 ? book.value!.sheets[activeIdx.value].rows : []))
const colCount = computed(() => sheetRows.value.reduce((m, r) => Math.max(m, r.length), 0))
/** 表头行数（多行表头）：data 里的 header_rows，缺省 1；展示时夹进实际行数 */
const headerCount = computed(() => {
  const sheet = activeIdx.value >= 0 ? book.value!.sheets[activeIdx.value] : null
  return Math.min(Math.max(1, sheet?.header_rows ?? 1), sheetRows.value.length || 1)
})
/** 列名 = 该列各行表头的非空内容用「 / 」拼接（多行表头），全空回退「列 N」。
 *  拼接按**新行在前**（行倒序）：「增加表头行」纳入的行拼在原表头前面——
 *  后加的行是上层字段，列名读作「上层 / 下层」。 */
const headerLabels = computed(() =>
  Array.from({ length: colCount.value }, (_, c) => {
    const parts = sheetRows.value
      .slice(0, headerCount.value)
      .reverse()
      .map((r) => r[c])
      .filter((v) => v !== null && v !== undefined && v !== '')
      .map((v) => String(v))
    return parts.length ? parts.join(' / ') : `列 ${c + 1}`
  }),
)
const bodyRows = computed(() =>
  sheetRows.value.slice(headerCount.value).map((cells, i) => ({ cells, gridRow: i + headerCount.value })),
)

/**
 * 网格动态列的列键（列宽 / 列设置偏好的列标识）：按表分域（s<表序>）、按列序追加。
 * 列只经「添加列」追加、从不删除/中间插入，键不会串位；隐藏列与列顺序走
 * DataTable 的列设置弹窗（只影响展示，数据与导出顺序不动）。
 */
const gridColKey = (colIdx: number) => `s${activeIdx.value}c${colIdx}`

const cellAt = (cells: SheetCellValue[], c: number): SheetCellValue => cells[c] ?? null
const cellText = (v: SheetCellValue) => (v === null || v === undefined ? '' : String(v))

// ── 单元格编辑（双击进入；回车/失焦提交，Esc 取消） ─────────────────────────

const editing = ref<{ sheet: number; row: number; col: number } | null>(null)
const editText = ref('')
let editInputEl: { focus: () => void } | null = null

const setEditInput = (el: unknown) => {
  editInputEl = el as { focus: () => void } | null
}

const isEditing = (gridRow: number, col: number) =>
  editing.value !== null &&
  editing.value.sheet === activeIdx.value &&
  editing.value.row === gridRow &&
  editing.value.col === col

/** 与上次保存快照不一致 = 未保存改动（高亮） */
const isDirtyCell = (gridRow: number, col: number) => {
  const cur = cellAt(sheetRows.value[gridRow] ?? [], col)
  const old = cellAt(saved.value?.sheets[activeIdx.value]?.rows?.[gridRow] ?? [], col)
  return JSON.stringify(cur) !== JSON.stringify(old)
}

const startEdit = (gridRow: number, col: number) => {
  editing.value = { sheet: activeIdx.value, row: gridRow, col }
  editText.value = cellText(cellAt(sheetRows.value[gridRow] ?? [], col))
  nextTick(() => editInputEl?.focus())
}

const cancelEdit = () => {
  editing.value = null
}

const commitCell = () => {
  const edit = editing.value
  if (!edit || !book.value) return
  const text = editText.value
  // 纯数字文本保持数字类型（"1.50" 这种会被 Number() 丢精度的写法维持字符串），空串清空为 null
  const value: SheetCellValue =
    text === '' ? null : /^-?\d+(\.\d+)?$/.test(text) && String(Number(text)) === text ? Number(text) : text
  const rows = book.value.sheets[edit.sheet].rows
  const row = rows[edit.row]
  while (row.length <= edit.col) row.push(null)
  row[edit.col] = value
  editing.value = null
  dirty.value = true
}

// ── 行列操作 ──────────────────────────────────────────────────────────────

const addRow = () => {
  if (!book.value || activeIdx.value < 0) return
  const rows = sheetRows.value
  if (rows.length === 0) rows.push([])
  rows.push(new Array(colCount.value).fill(null))
  dirty.value = true
}

const removeRow = (gridRow: number) => {
  sheetRows.value.splice(gridRow, 1)
  dirty.value = true
}

// ── 表头编辑（多行表头：纳入下一行 / 删行（≥1）/ 编辑内容 / 添加列） ─────────

const headerVisible = ref(false)
/** 对话框草稿：表头块各行（确定时整块写回） */
const headerDraft = ref<SheetCellValue[][]>([])
/** 草稿里从数据区纳入了几行表头（确定时这些行随表头块一起写回） */
const headerConsumed = ref(0)

const cloneRow = (row: SheetCellValue[], width: number): SheetCellValue[] => {
  const copy = JSON.parse(JSON.stringify(row)) as SheetCellValue[]
  while (copy.length < width) copy.push(null)
  return copy
}

const openHeaderEditor = () => {
  const width = colCount.value
  headerDraft.value = sheetRows.value.slice(0, headerCount.value).map((r) => cloneRow(r, width))
  if (headerDraft.value.length === 0) headerDraft.value.push(new Array(width).fill(null))
  headerConsumed.value = 0
  headerVisible.value = true
}

/** 指定多行为表头：把下一行数据行纳入表头（内容不动）；没有数据行就补一行空表头 */
const addHeaderRow = () => {
  const next = sheetRows.value[headerCount.value + headerConsumed.value]
  if (next) {
    headerDraft.value.push(cloneRow(next, colCount.value))
    headerConsumed.value += 1
  } else {
    const width = Math.max(colCount.value, headerDraft.value[0]?.length ?? 0)
    headerDraft.value.push(new Array(width).fill(null))
  }
}

/** 删除表头行（整行删除）；至少保留 1 行表头 */
const removeHeaderRow = (idx: number) => {
  if (headerDraft.value.length <= 1) return
  headerDraft.value.splice(idx, 1)
}

const addHeaderColumn = () => {
  headerDraft.value.forEach((r) => r.push(null))
}

const commitHeader = () => {
  if (!book.value || activeIdx.value < 0) return
  const sheet = book.value.sheets[activeIdx.value]
  // 表头块 + 纳入过的数据行整体替换为草稿：删除的行即消失、纳入的行原位进表头
  sheet.rows.splice(0, headerCount.value + headerConsumed.value, ...headerDraft.value)
  if (headerDraft.value.length > 1) sheet.header_rows = headerDraft.value.length
  else delete sheet.header_rows
  headerVisible.value = false
  dirty.value = true
}

// ── 保存（落新版本 + 修改历史） ────────────────────────────────────────────

const saveDialogVisible = ref(false)
const saveNote = ref('')
const saving = ref(false)

const openSaveDialog = () => {
  saveNote.value = ''
  saveDialogVisible.value = true
}

const doSave = async () => {
  if (!book.value) return
  saving.value = true
  try {
    const res = (await saveSpreadsheet(bookId.value, book.value, saveNote.value.trim() || undefined)).data
    saveDialogVisible.value = false
    if (res.created) {
      ElMessage.success(
        `已保存为版本 v${res.revision}：修改 ${res.summary.cells_changed} 格、新增 ${res.summary.rows_added} 行、删除 ${res.summary.rows_removed} 行`,
      )
    } else {
      ElMessage.info('没有改动，未产生新版本')
    }
    saved.value = JSON.parse(JSON.stringify(book.value)) as SpreadsheetData
    dirty.value = false
    latestRevision.value = res.revision
    if (historyVisible.value) await loadRevisions()
  } catch (e) {
    const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    ElMessage.error(detail ? `保存失败：${detail}` : '保存失败，请稍后重试')
  } finally {
    saving.value = false
  }
}

// ── 导出（当前版本 / 历史版本） ────────────────────────────────────────────

const saveAs = (data: Blob, filename: string) => {
  const url = URL.createObjectURL(data)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

const onExport = async (revision?: number) => {
  try {
    const res = await exportSpreadsheet(bookId.value, revision)
    const suffix = revision === undefined ? '' : `-v${revision}`
    saveAs(res.data as Blob, `${name.value}${suffix}.xlsx`)
  } catch {
    ElMessage.error('导出失败，请稍后重试')
  }
}

// ── 修改历史（列表 / 差异明细 / 回滚） ─────────────────────────────────────

const historyVisible = ref(false)
const revisions = ref<SpreadsheetRevision[]>([])
const revisionsLoading = ref(false)
const changesVisible = ref(false)
const changesDetail = ref<SpreadsheetRevisionDetail | null>(null)
const restoring = ref(false)

const loadRevisions = async () => {
  revisionsLoading.value = true
  try {
    revisions.value = (await getSpreadsheetRevisions(bookId.value)).data.results
  } catch {
    ElMessage.error('修改历史获取失败')
  } finally {
    revisionsLoading.value = false
  }
}

const openHistory = async () => {
  historyVisible.value = true
  await loadRevisions()
}

const showChanges = async (revision: number) => {
  try {
    changesDetail.value = (await getSpreadsheetRevision(bookId.value, revision)).data
    changesVisible.value = true
  } catch {
    ElMessage.error('版本详情获取失败')
  }
}

const summaryText = (s: SheetChangeSummary) => {
  const parts = [`修改 ${s.cells_changed} 格`, `增 ${s.rows_added} 行`, `删 ${s.rows_removed} 行`]
  if (s.sheets_added) parts.push(`增 ${s.sheets_added} 张表`)
  if (s.sheets_removed) parts.push(`删 ${s.sheets_removed} 张表`)
  if (s.header_rows_changed) parts.push(`表头行数变更 ${s.header_rows_changed} 张表`)
  return parts.join(' · ') + (s.truncated ? '（明细已截断）' : '')
}

const changePos = (rowIdx: number, colIdx: number) => `第 ${rowIdx + 1} 行 · 第 ${colIdx + 1} 列`
const changeVal = (v: SheetCellValue) => (v === null || v === undefined ? '（空）' : String(v))

const restoreRevision = async (revision: number) => {
  try {
    await ElMessageBox.confirm(
      dirty.value
        ? `恢复到版本 v${revision}？当前未保存的修改将被覆盖。`
        : `恢复到版本 v${revision}？将以一次新保存落地，历史不会被改写。`,
      '恢复确认',
      { type: 'warning' },
    )
  } catch {
    return
  }
  restoring.value = true
  try {
    const res = (await restoreSpreadsheetRevision(bookId.value, revision)).data
    if (res.created) {
      ElMessage.success(`已恢复到版本 v${revision}，当前版本 v${res.revision}`)
    } else {
      ElMessage.info('当前内容与该版本一致，无需恢复')
    }
    await loadBook()
    changesVisible.value = false
    if (historyVisible.value) await loadRevisions()
  } catch (e) {
    const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    ElMessage.error(detail ? `恢复失败：${detail}` : '恢复失败，请稍后重试')
  } finally {
    restoring.value = false
  }
}

// ── 加载 / 离开守卫 ────────────────────────────────────────────────────────

const loadBook = async () => {
  loading.value = true
  try {
    const detail = (await getSpreadsheet(bookId.value)).data
    name.value = detail.name
    latestRevision.value = detail.latest_revision
    book.value = JSON.parse(JSON.stringify(detail.data)) as SpreadsheetData
    saved.value = JSON.parse(JSON.stringify(detail.data)) as SpreadsheetData
    dirty.value = false
    if (!detail.data.sheets.some((s) => s.name === activeName.value)) {
      activeName.value = detail.data.sheets[0]?.name ?? ''
    }
  } catch {
    ElMessage.error('表格加载失败')
    router.push({ name: 'docs-spreadsheet' })
  } finally {
    loading.value = false
  }
}

onMounted(loadBook)

onBeforeRouteLeave(async () => {
  if (!dirty.value) return true
  try {
    await ElMessageBox.confirm('有未保存的修改，离开将丢失。确定离开？', '未保存提醒', { type: 'warning' })
    return true
  } catch {
    return false
  }
})
</script>

<template>
  <PageLayout :title="name || '电子表格'">
    <template #actions>
      <el-tag v-if="dirty" type="warning">未保存</el-tag>
      <el-button @click="router.push({ name: 'docs-spreadsheet' })">返回列表</el-button>
      <el-button @click="onExport()">导出 xlsx</el-button>
      <el-button @click="openHistory">修改历史</el-button>
      <el-button type="primary" @click="openSaveDialog">保存</el-button>
    </template>

    <div class="editor">
      <el-tabs v-model="activeName" class="sheet-tabs">
        <el-tab-pane v-for="sheet in book?.sheets ?? []" :key="sheet.name" :label="sheet.name" :name="sheet.name" />
      </el-tabs>

      <div class="toolbar">
        <el-button size="small" @click="addRow">添加行</el-button>
        <el-button size="small" @click="openHeaderEditor">编辑表头</el-button>
        <span class="hint">
          双击单元格编辑，回车/失焦提交、Esc 取消；蓝底格是未保存的修改；列名过长自动截断、悬停看全文；右上「列设置」可隐藏列 / 拖拽调列序（仅展示，不动数据）
        </span>
      </div>

      <div class="grid-wrap">
        <DataTable :data="bodyRows" :loading="loading" :table-key="TABLE_KEYS.spreadsheetGrid">
          <DataColumn type="index" column-key="row-index" label="#" :width="56" fixed="left" default-hidden />
          <DataColumn
            v-for="(label, colIdx) in headerLabels"
            :key="gridColKey(colIdx)"
            :column-key="gridColKey(colIdx)"
            :label="label"
            :min-width="130"
          >
            <template #header>
              <span class="header-cell" :title="label">{{ label }}</span>
            </template>
            <template #default="{ row }">
              <el-input
                v-if="isEditing(row.gridRow, colIdx)"
                :ref="setEditInput"
                v-model="editText"
                size="small"
                @keydown.enter="commitCell"
                @keydown.esc="cancelEdit"
                @blur="commitCell"
              />
              <div
                v-else
                class="cell"
                :class="{ 'cell-dirty': isDirtyCell(row.gridRow, colIdx) }"
                @dblclick="startEdit(row.gridRow, colIdx)"
              >
                {{ cellText(cellAt(row.cells, colIdx)) }}
              </div>
            </template>
          </DataColumn>
          <DataColumn label="操作" :width="80" fixed="right">
            <template #default="{ row }">
              <el-button link type="danger" @click="removeRow(row.gridRow)">删除</el-button>
            </template>
          </DataColumn>
        </DataTable>
      </div>
    </div>
  </PageLayout>

  <!-- 表头编辑：多行表头块——每行可改内容/删除（至少留 1 行），可纳入下一行或加列 -->
  <el-dialog v-model="headerVisible" title="编辑表头" width="760px">
    <div class="header-hint">表头共 {{ headerDraft.length }} 行；列名取该列各行非空内容按「新行在前」拼接，过长截断展示</div>
    <div v-for="(draftRow, ri) in headerDraft" :key="ri" class="header-row">
      <span class="header-col-no">第 {{ ri + 1 }} 行</span>
      <el-input
        v-for="(_, ci) in draftRow"
        :key="ci"
        class="header-cell-input"
        :model-value="cellText(headerDraft[ri][ci])"
        :placeholder="`列 ${ci + 1}`"
        @update:model-value="(v) => (headerDraft[ri][ci] = v)"
      />
      <el-button link type="danger" :disabled="headerDraft.length <= 1" @click="removeHeaderRow(ri)">删除</el-button>
    </div>
    <div class="header-actions">
      <el-button size="small" @click="addHeaderRow">＋ 增加表头行</el-button>
      <el-button size="small" @click="addHeaderColumn">＋ 添加列</el-button>
    </div>
    <template #footer>
      <el-button @click="headerVisible = false">取消</el-button>
      <el-button type="primary" @click="commitHeader">确定</el-button>
    </template>
  </el-dialog>

  <!-- 保存：变更说明记入修改历史 -->
  <el-dialog v-model="saveDialogVisible" title="保存修改" width="480px">
    <el-input v-model="saveNote" type="textarea" :rows="3" placeholder="变更说明（可选，会记入修改历史）" />
    <template #footer>
      <el-button @click="saveDialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="doSave">保存</el-button>
    </template>
  </el-dialog>

  <!-- 修改历史：列表 + 差异明细 + 回滚 / 导出历史版本 -->
  <el-drawer v-model="historyVisible" title="修改历史" size="720px">
    <DataTable :data="revisions" :loading="revisionsLoading">
      <DataColumn prop="revision" label="版本" :width="70" anchor>
        <template #default="{ row }">v{{ row.revision }}</template>
      </DataColumn>
      <DataColumn prop="created_at" label="保存时间" :min-width="150">
        <template #default="{ row }">{{ new Date(row.created_at).toLocaleString('zh-CN') }}</template>
      </DataColumn>
      <DataColumn prop="created_by" label="操作人" :min-width="90">
        <template #default="{ row }">{{ row.created_by || '—' }}</template>
      </DataColumn>
      <DataColumn prop="note" label="变更说明" :min-width="150" show-overflow-tooltip />
      <DataColumn label="变更摘要" :min-width="190">
        <template #default="{ row }">{{ summaryText(row.summary) }}</template>
      </DataColumn>
      <DataColumn label="操作" :width="190" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="showChanges(row.revision)">查看差异</el-button>
          <el-button link type="primary" @click="onExport(row.revision)">导出</el-button>
          <el-button
            link
            type="warning"
            :disabled="row.revision === latestRevision || restoring"
            @click="restoreRevision(row.revision)"
          >
            恢复
          </el-button>
        </template>
      </DataColumn>
    </DataTable>
  </el-drawer>

  <!-- 单个版本的变更明细（相对上一版本） -->
  <el-dialog v-model="changesVisible" :title="`版本 v${changesDetail?.revision ?? ''} 变更明细`" width="720px">
    <div v-if="changesDetail" class="rev-meta">
      <span>{{ new Date(changesDetail.created_at).toLocaleString('zh-CN') }}</span>
      <span>{{ changesDetail.created_by || '—' }}</span>
      <span>{{ changesDetail.note || '（无说明）' }}</span>
    </div>
    <DataTable :data="changesDetail?.changes ?? []">
      <DataColumn prop="sheet" label="工作表" :min-width="110" anchor />
      <DataColumn label="位置" :width="140">
        <template #default="{ row }">{{ changePos(row.row, row.col) }}</template>
      </DataColumn>
      <DataColumn label="原值" :min-width="150">
        <template #default="{ row }">{{ changeVal(row.old) }}</template>
      </DataColumn>
      <DataColumn label="新值" :min-width="150">
        <template #default="{ row }">{{ changeVal(row.new) }}</template>
      </DataColumn>
    </DataTable>
    <template #footer>
      <el-button @click="onExport(changesDetail?.revision)">导出该版本</el-button>
      <el-button
        v-if="changesDetail"
        type="warning"
        :disabled="restoring || changesDetail.revision === latestRevision"
        @click="restoreRevision(changesDetail.revision)"
      >
        恢复到该版本
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.editor { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-shrink: 0; }
.hint { color: var(--el-text-color-secondary); font-size: 12px; }
.grid-wrap { flex: 1; min-height: 0; background: var(--el-bg-color); border-radius: 8px; overflow: hidden; }
.cell {
  min-height: 24px; line-height: 24px; padding: 0 4px; cursor: text;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cell-dirty { background: var(--el-color-primary-light-9); }
/* 列名截断展示（表头内容允许截断），全文在 title 悬停 */
.header-cell { display: block; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.header-hint { margin-bottom: 10px; color: var(--el-text-color-secondary); font-size: 12px; }
.header-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 8px; }
.header-col-no { width: 56px; flex-shrink: 0; color: var(--el-text-color-secondary); font-size: 12px; }
.header-cell-input { width: 150px; }
.header-actions { margin-top: 4px; }
.rev-meta { display: flex; gap: 12px; margin-bottom: 8px; color: var(--el-text-color-secondary); font-size: 12px; }
</style>
