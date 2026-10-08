<script setup lang="ts">
import CodeDiffView from '@/components/CodeDiffView.vue'
import { getGitConfigContent, getGitDiff, getConfigHistory } from '@/api/devices'

const props = defineProps<{
  visible: boolean
  deviceId: number
  hostname: string
}>()
const emit = defineEmits<{ 'update:visible': [v: boolean] }>()

const history = ref<any[]>([])
const oldHash = ref('')
const newHash = ref('')
const diffText = ref('')
const oldText = ref('')
const newText = ref('')
const loading = ref(false)

const fetchHistory = async () => {
  try {
    const res = await getConfigHistory(props.hostname)
    history.value = res.data.history || []
  } catch {
    history.value = []
  }
}

const fetchDiff = async () => {
  if (!oldHash.value || !newHash.value || !props.hostname) return
  loading.value = true
  try {
    // 全文喂组件显示完整配置；后端 diff 只用来判空态（unified diff 只带变更±3行）
    const [oldRes, newRes, diffRes] = await Promise.all([
      getGitConfigContent(props.hostname, oldHash.value),
      getGitConfigContent(props.hostname, newHash.value),
      getGitDiff(props.hostname, oldHash.value, newHash.value),
    ])
    oldText.value = oldRes.data.config_text || ''
    newText.value = newRes.data.config_text || ''
    diffText.value = diffRes.data.diff || ''
  } catch {
    ElMessage.error('获取配置失败')
  } finally {
    loading.value = false
  }
}

const handleClose = () => {
  oldHash.value = ''
  newHash.value = ''
  diffText.value = ''
  oldText.value = ''
  newText.value = ''
  emit('update:visible', false)
}

watch(() => props.visible, (v) => { if (v) fetchHistory() })
watch([oldHash, newHash], () => { if (oldHash.value && newHash.value) fetchDiff() })
</script>

<template>
  <el-dialog :model-value="visible" title="配置对比" width="75%" top="5vh" @close="handleClose">
    <div class="compare-body" v-loading="loading">
      <CodeDiffView
        :diff="diffText"
        :old-text="oldText"
        :new-text="newText"
        :filename="oldHash.slice(0, 8)"
        :new-filename="newHash.slice(0, 8)"
      >
        <!-- toolbar 插槽：选择器 + 导航 + 统计 + 切换，与选择配置同一元素；选择器始终可见 -->
        <template #toolbar="{ addNum, delNum, prev, next, outputFormat, setOutputFormat }">
          <div class="compare-selectors">
            <el-select v-model="oldHash" placeholder="选择基准版本" style="width: 240px" filterable>
              <el-option v-for="h in history" :key="h.full_hash"
                :label="`${new Date(h.date).toLocaleString('zh-CN')} — ${h.hash}`"
                :value="h.full_hash" />
            </el-select>
            <span class="arrow">→</span>
            <el-select v-model="newHash" placeholder="选择对比版本" style="width: 240px" filterable>
              <el-option v-for="h in history" :key="h.full_hash"
                :label="`${new Date(h.date).toLocaleString('zh-CN')} — ${h.hash}`"
                :value="h.full_hash" />
            </el-select>

            <!-- 选齐两版且有变更才显示导航/统计（否则是空态，无需工具栏） -->
            <span v-if="oldHash && newHash && diffText" class="toolbar-right">
              <span class="nav-group">
                <el-button size="small" @click="prev">↑</el-button>
                <el-button size="small" @click="next">↓</el-button>
              </span>
              <span class="diff-stat">
                <span class="stat-added">+{{ addNum }} additions</span>
                <span class="stat-deleted">-{{ delNum }} deletions</span>
              </span>
              <el-radio-group :model-value="outputFormat" size="small" @update:model-value="setOutputFormat">
                <el-radio-button value="side-by-side">并排</el-radio-button>
                <el-radio-button value="line-by-line">行对行</el-radio-button>
              </el-radio-group>
            </span>
          </div>
        </template>

        <template #empty>
          <div class="diff-empty">
            {{ oldHash && newHash ? '两个版本相同，无变更' : '请选择两个版本进行对比' }}
          </div>
        </template>
      </CodeDiffView>
    </div>
  </el-dialog>
</template>

<style scoped>
.compare-selectors {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
  flex-shrink: 0;
}
.arrow {
  font-size: 16px;
  color: #909399;
}
/* 工具栏右半：导航 + 统计 + 切换，靠右对齐 */
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-left: auto;
}
.nav-group {
  display: inline-flex;
  gap: 4px;
}
.diff-stat {
  display: inline-flex;
  gap: 10px;
  font-size: 12px;
  font-family: monospace;
}
.stat-added {
  color: var(--el-color-success);
}
.stat-deleted {
  color: var(--el-color-danger);
}
.compare-body {
  height: 65vh;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overflow: hidden;
}
.diff-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #909399;
}
</style>
