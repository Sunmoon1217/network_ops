<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Upload } from '@element-plus/icons-vue'
import {
  deleteDocument,
  downloadDocument,
  getDocument,
  getDocumentRevision,
  getDocumentRevisions,
  getDocuments,
  previewDocument,
  pushDocument,
  reconvertDocument,
  restoreDocumentRevision,
  syncDocumentStatus,
  updateDocument,
  uploadDocument,
} from '@/api/documents'
import PageLayout from '@/components/PageLayout.vue'
import DataTable from '@/components/DataTable.vue'
import DataColumn from '@/components/DataColumn.vue'
import { TABLE_KEYS } from '@/constants/tableKeys'
import type { DocDetail, DocRevision, DocSummary } from '@/types'

// ---------------------------------------------------------------------------
// 知识库（文档转换 + Dify 推送）：上传转换 → 查看/编辑产物/替换源文件重转 →
// 手动推送（已推送文档改完走 update 原地更新）；版本快照可查看/回滚。
// ---------------------------------------------------------------------------

const rows = ref<DocSummary[]>([])
const loading = ref(false)

const load = async () => {
  loading.value = true
  try {
    rows.value = (await getDocuments()).data.results
  } catch {
    ElMessage.error('文档列表获取失败')
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

const errDetail = (e: unknown, fallback: string) => {
  const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
  ElMessage.error(detail ? `${fallback}：${detail}` : fallback)
}

// ---------------------------------------------------------------------------
// 上传转换（主文档 + 图片附件）
// ---------------------------------------------------------------------------

const uploadOpen = ref(false)
const uploading = ref(false)
const uploadMain = ref<File | null>(null)
const uploadAtts = ref<File[]>([])

const onMainChange = (f: { raw?: File }) => {
  if (f.raw) uploadMain.value = f.raw
}
const onAttChange = (f: { raw?: File }) => {
  if (f.raw && !uploadAtts.value.some((a) => a.name === f.raw!.name)) uploadAtts.value.push(f.raw)
}
const onUpload = async () => {
  if (!uploadMain.value || uploading.value) return
  uploading.value = true
  try {
    const detail = (await uploadDocument(uploadMain.value, uploadAtts.value)).data
    ElMessage.success(`已转换「${detail.name}」为 ${detail.target_format}`)
    uploadOpen.value = false
    uploadMain.value = null
    uploadAtts.value = []
    await load()
  } catch (e) {
    errDetail(e, '上传转换失败')
  } finally {
    uploading.value = false
  }
}

// ---------------------------------------------------------------------------
// 查看（沙箱预览 / 源码）
// ---------------------------------------------------------------------------

const viewOpen = ref(false)
const viewLoading = ref(false)
const current = ref<DocDetail | null>(null)
const viewTab = ref<'preview' | 'source'>('preview')
const previewHtml = ref('')

const openView = async (id: number) => {
  viewTab.value = 'preview'
  previewHtml.value = ''
  viewOpen.value = true
  viewLoading.value = true
  try {
    current.value = (await getDocument(id)).data
    if (current.value.target_format !== 'pdf') previewHtml.value = (await previewDocument(id)).data.html
  } catch (e) {
    errDetail(e, '文档获取失败')
  } finally {
    viewLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// 编辑转换产物
// ---------------------------------------------------------------------------

const editOpen = ref(false)
const editSaving = ref(false)
const editText = ref('')
const editNote = ref('')

const openEdit = async (id: number) => {
  try {
    const detail = (await getDocument(id)).data
    current.value = detail
    editText.value = detail.converted
    editNote.value = ''
    editOpen.value = true
  } catch (e) {
    errDetail(e, '文档详情获取失败')
  }
}
const onSaveEdit = async () => {
  if (!current.value || editSaving.value) return
  editSaving.value = true
  try {
    const result = (await updateDocument(current.value.id, editText.value, editNote.value)).data
    ElMessage.success(`已保存为版本 v${result.revision}${result.pending_sync ? '，待同步到知识库' : ''}`)
    editOpen.value = false
    await load()
  } catch (e) {
    errDetail(e, '保存失败')
  } finally {
    editSaving.value = false
  }
}

// ---------------------------------------------------------------------------
// 重新转换（替换源文件）
// ---------------------------------------------------------------------------

const reconvertOpen = ref(false)
const reconverting = ref(false)
const reconvertFile = ref<File | null>(null)
const reconvertAtts = ref<File[]>([])
const reconvertNote = ref('')

const openReconvert = async (id: number) => {
  try {
    current.value = (await getDocument(id)).data
  } catch (e) {
    errDetail(e, '文档详情获取失败')
    return
  }
  reconvertFile.value = null
  reconvertAtts.value = []
  reconvertNote.value = ''
  reconvertOpen.value = true
}
const onReconvertFileChange = (f: { raw?: File }) => {
  if (f.raw) reconvertFile.value = f.raw
}
const onReconvertAttChange = (f: { raw?: File }) => {
  if (f.raw && !reconvertAtts.value.some((a) => a.name === f.raw!.name)) reconvertAtts.value.push(f.raw)
}
const onReconvert = async () => {
  if (!current.value || !reconvertFile.value || reconverting.value) return
  reconverting.value = true
  try {
    const result = (await reconvertDocument(current.value.id, reconvertFile.value, reconvertAtts.value, reconvertNote.value)).data
    ElMessage.success(`已重新转换为版本 v${result.revision}${result.pending_sync ? '，待同步到知识库' : ''}`)
    reconvertOpen.value = false
    await load()
  } catch (e) {
    errDetail(e, '重新转换失败')
  } finally {
    reconverting.value = false
  }
}

// ---------------------------------------------------------------------------
// 版本历史（查看快照 / 回滚）
// ---------------------------------------------------------------------------

const historyOpen = ref(false)
const historyLoading = ref(false)
const revisions = ref<DocRevision[]>([])
const snapshotOpen = ref(false)
const snapshotText = ref('')
const snapshotTitle = ref('')

const openHistory = async (id: number) => {
  historyOpen.value = true
  historyLoading.value = true
  try {
    current.value = (await getDocument(id)).data
    revisions.value = (await getDocumentRevisions(id)).data.results
  } catch (e) {
    errDetail(e, '版本历史获取失败')
  } finally {
    historyLoading.value = false
  }
}
const onViewSnapshot = async (revision: number) => {
  if (!current.value) return
  try {
    const detail = (await getDocumentRevision(current.value.id, revision)).data
    snapshotText.value = detail.converted
    snapshotTitle.value = `版本 v${revision} 产物快照`
    snapshotOpen.value = true
  } catch (e) {
    errDetail(e, '快照获取失败')
  }
}
const onRestore = async (revision: number) => {
  if (!current.value) return
  try {
    await ElMessageBox.confirm(`确定恢复到版本 v${revision}？将以一次新版本落地，历史不被改写。`, '恢复确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    const result = (await restoreDocumentRevision(current.value.id, revision)).data
    ElMessage.success(`已恢复为版本 v${result.revision}${result.pending_sync ? '，待同步到知识库' : ''}`)
    historyOpen.value = false
    await load()
  } catch (e) {
    errDetail(e, '恢复失败')
  }
}

// ---------------------------------------------------------------------------
// 推送 / 状态同步 / 下载 / 删除
// ---------------------------------------------------------------------------

const pushing = ref<number | null>(null)

const onPush = async (id: number, name: string, wasPushed: boolean) => {
  pushing.value = id
  try {
    await pushDocument(id)
    ElMessage.success(wasPushed ? `已更新知识库「${name}」` : `已推送「${name}」到知识库`)
    await load()
  } catch (e) {
    errDetail(e, '推送失败')
    await load()
  } finally {
    pushing.value = null
  }
}

const onSyncStatus = async (id: number) => {
  try {
    const detail = (await syncDocumentStatus(id)).data
    ElMessage.success(`索引状态：${detail.dify_indexing_status || '未知'}`)
    await load()
  } catch (e) {
    errDetail(e, '状态同步失败')
  }
}

const onDownload = async (id: number, name: string) => {
  try {
    const res = await downloadDocument(id)
    saveAs(res.data as Blob, name)
  } catch (e) {
    errDetail(e, '下载失败')
  }
}

const onDelete = async (id: number, name: string) => {
  try {
    await ElMessageBox.confirm(`确定删除「${name}」？版本历史一并移除，此操作不可恢复。`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteDocument(id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    errDetail(e, '删除失败')
  }
}

onMounted(load)
</script>

<template>
  <PageLayout title="知识库">
    <template #actions>
      <el-button type="primary" @click="uploadOpen = true">
        <el-icon><Upload /></el-icon>
        上传文档
      </el-button>
    </template>

    <DataTable :data="rows" :loading="loading" :table-key="TABLE_KEYS.docsKnowledge">
      <DataColumn prop="name" label="文件名" :min-width="220" anchor />
      <DataColumn label="转换" :min-width="130">
        <template #default="{ row }">
          <el-tag size="small" type="info">{{ row.source_format }}</el-tag>
          <span style="margin: 0 4px">→</span>
          <el-tag size="small">{{ row.target_format }}</el-tag>
          <el-tag v-if="row.has_images" size="small" type="warning" style="margin-left: 4px">含图</el-tag>
        </template>
      </DataColumn>
      <DataColumn label="状态" :min-width="120">
        <template #default="{ row }">
          <el-tag v-if="row.status === 'pushed'" size="small" type="success">已推送</el-tag>
          <el-tag v-else-if="row.status === 'push_failed'" size="small" type="danger">推送失败</el-tag>
          <el-tag v-else size="small" type="info">待推送</el-tag>
          <el-tag v-if="row.pending_sync" size="small" type="warning" style="margin-left: 4px">待同步</el-tag>
        </template>
      </DataColumn>
      <DataColumn prop="latest_revision" label="版本" :width="70" />
      <DataColumn label="人工修改" :width="90">
        <template #default="{ row }">{{ row.edited ? '是' : '否' }}</template>
      </DataColumn>
      <DataColumn label="索引状态" :min-width="100">
        <template #default="{ row }">{{ row.dify_indexing_status || '—' }}</template>
      </DataColumn>
      <DataColumn prop="updated_at" label="更新时间" :min-width="150">
        <template #default="{ row }">{{ new Date(row.updated_at).toLocaleString('zh-CN') }}</template>
      </DataColumn>
      <DataColumn prop="created_by" label="创建人" :min-width="90">
        <template #default="{ row }">{{ row.created_by || '—' }}</template>
      </DataColumn>
      <DataColumn label="操作" :width="300" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openView(row.id)">查看</el-button>
          <el-button v-if="row.target_format !== 'pdf'" link type="primary" @click="openEdit(row.id)">编辑</el-button>
          <el-button link type="primary" @click="openReconvert(row.id)">重转</el-button>
          <el-button link type="primary" @click="openHistory(row.id)">历史</el-button>
          <el-button v-if="row.status !== 'pushed' || row.pending_sync" link type="success" :loading="pushing === row.id" @click="onPush(row.id, row.name, row.status === 'pushed')">
            {{ row.status === 'pushed' ? '同步' : '推送' }}
          </el-button>
          <el-button v-else link type="info" @click="onSyncStatus(row.id)">状态</el-button>
          <el-button link type="primary" @click="onDownload(row.id, row.name)">下载</el-button>
          <el-button link type="danger" @click="onDelete(row.id, row.name)">删除</el-button>
        </template>
      </DataColumn>
    </DataTable>

    <!-- 上传转换 -->
    <el-dialog v-model="uploadOpen" title="上传文档" width="560px">
      <el-form label-width="90px">
        <el-form-item label="主文档">
          <el-upload :show-file-list="false" :auto-upload="false" accept=".txt,.md,.docx,.html,.htm,.pdf,.xlsx,.csv" :on-change="onMainChange">
            <el-button><el-icon><Upload /></el-icon>选择文件</el-button>
          </el-upload>
          <span v-if="uploadMain" style="margin-left: 8px">{{ uploadMain.name }}</span>
        </el-form-item>
        <el-form-item label="图片附件">
          <el-upload :show-file-list="false" :auto-upload="false" multiple accept="image/*" :on-change="onAttChange">
            <el-button>选择图片</el-button>
          </el-upload>
          <div v-if="uploadAtts.length" style="margin-left: 8px">
            <el-tag v-for="a in uploadAtts" :key="a.name" size="small" closable @close="uploadAtts = uploadAtts.filter((x) => x.name !== a.name)" style="margin: 2px">
              {{ a.name }}
            </el-tag>
          </div>
        </el-form-item>
        <el-form-item label=" ">
          <span style="color: var(--el-text-color-secondary); font-size: 12px">
            md/html 引用的本地图片随附件上传；无图转 md，含图转自包含 html，pdf 直传
          </span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadOpen = false">取消</el-button>
        <el-button type="primary" :loading="uploading" :disabled="!uploadMain" @click="onUpload">上传转换</el-button>
      </template>
    </el-dialog>

    <!-- 查看（沙箱预览 / 源码） -->
    <el-dialog v-model="viewOpen" :title="current?.name || '查看'" width="820px" top="6vh">
      <el-tabs v-model="viewTab">
        <el-tab-pane label="预览" name="preview">
          <div v-if="current?.target_format === 'pdf'" style="padding: 24px; text-align: center; color: var(--el-text-color-secondary)">
            pdf 直传无转换产物，请下载源文件查看
            <div style="margin-top: 12px">
              <el-button type="primary" @click="current && onDownload(current.id, current.name)">下载源文件</el-button>
            </div>
          </div>
          <div v-loading="viewLoading" style="height: 55vh; border: 1px solid var(--el-border-color-lighter); border-radius: 4px; overflow: hidden">
            <!-- 用户可编辑的 html 产物可能含脚本：sandbox 全禁，只当静态渲染 -->
            <iframe v-if="previewHtml" sandbox="" :srcdoc="previewHtml" style="width: 100%; height: 100%; border: none"></iframe>
          </div>
        </el-tab-pane>
        <el-tab-pane label="源码" name="source">
          <pre class="doc-source">{{ current?.converted || '（无产物）' }}</pre>
        </el-tab-pane>
      </el-tabs>
    </el-dialog>

    <!-- 编辑转换产物 -->
    <el-dialog v-model="editOpen" :title="`编辑产物 - ${current?.name || ''}`" width="820px" top="6vh">
      <el-input v-model="editText" type="textarea" :rows="18" style="font-family: monospace" />
      <el-input v-model="editNote" placeholder="变更说明（可选）" style="margin-top: 8px" />
      <template #footer>
        <el-button @click="editOpen = false">取消</el-button>
        <el-button type="primary" :loading="editSaving" @click="onSaveEdit">保存（落新版本）</el-button>
      </template>
    </el-dialog>

    <!-- 重新转换 -->
    <el-dialog v-model="reconvertOpen" :title="`替换源文件重转 - ${current?.name || ''}`" width="560px">
      <el-form label-width="90px">
        <el-form-item label="新源文件">
          <el-upload :show-file-list="false" :auto-upload="false" accept=".txt,.md,.docx,.html,.htm,.pdf,.xlsx,.csv" :on-change="onReconvertFileChange">
            <el-button><el-icon><Upload /></el-icon>选择文件</el-button>
          </el-upload>
          <span v-if="reconvertFile" style="margin-left: 8px">{{ reconvertFile.name }}</span>
        </el-form-item>
        <el-form-item label="图片附件">
          <el-upload :show-file-list="false" :auto-upload="false" multiple accept="image/*" :on-change="onReconvertAttChange">
            <el-button>选择图片</el-button>
          </el-upload>
          <div v-if="reconvertAtts.length" style="margin-left: 8px">
            <el-tag v-for="a in reconvertAtts" :key="a.name" size="small" closable @close="reconvertAtts = reconvertAtts.filter((x) => x.name !== a.name)" style="margin: 2px">
              {{ a.name }}
            </el-tag>
          </div>
        </el-form-item>
        <el-form-item label="变更说明">
          <el-input v-model="reconvertNote" placeholder="可选" />
        </el-form-item>
        <el-form-item label=" ">
          <span style="color: var(--el-color-warning); font-size: 12px">人工编辑过的产物会被新转换覆盖（旧产物仍在版本历史里可回滚）</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reconvertOpen = false">取消</el-button>
        <el-button type="primary" :loading="reconverting" :disabled="!reconvertFile" @click="onReconvert">重新转换</el-button>
      </template>
    </el-dialog>

    <!-- 版本历史 -->
    <el-drawer v-model="historyOpen" :title="`版本历史 - ${current?.name || ''}`" size="620px">
      <DataTable :data="revisions" :loading="historyLoading">
        <DataColumn prop="revision" label="版本" :width="70" anchor>
          <template #default="{ row }">v{{ row.revision }}</template>
        </DataColumn>
        <DataColumn prop="note" label="变更说明" :min-width="140" />
        <DataColumn label="来源" :width="90">
          <template #default="{ row }">
            <el-tag v-if="row.edited" size="small" type="warning">人工</el-tag>
            <el-tag v-else size="small" type="info">转换</el-tag>
          </template>
        </DataColumn>
        <DataColumn prop="created_at" label="保存时间" :min-width="150">
          <template #default="{ row }">{{ new Date(row.created_at).toLocaleString('zh-CN') }}</template>
        </DataColumn>
        <DataColumn label="操作" :width="130" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="onViewSnapshot(row.revision)">查看</el-button>
            <el-button link type="warning" @click="onRestore(row.revision)">恢复</el-button>
          </template>
        </DataColumn>
      </DataTable>
    </el-drawer>

    <!-- 版本快照 -->
    <el-dialog v-model="snapshotOpen" :title="snapshotTitle" width="720px" top="8vh">
      <pre class="doc-source">{{ snapshotText || '（无产物）' }}</pre>
    </el-dialog>
  </PageLayout>
</template>

<style scoped>
.doc-source {
  max-height: 60vh;
  overflow: auto;
  margin: 0;
  padding: 12px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  font-family: monospace;
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--el-text-color-regular);
}
</style>
