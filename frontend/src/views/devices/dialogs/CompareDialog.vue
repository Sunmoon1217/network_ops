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
    <div class="compare-selectors">
      <el-select v-model="oldHash" placeholder="选择基准版本" style="width: 260px" filterable>
        <el-option v-for="h in history" :key="h.full_hash"
          :label="`${new Date(h.date).toLocaleString('zh-CN')} — ${h.hash}`"
          :value="h.full_hash" />
      </el-select>
      <span class="arrow">→</span>
      <el-select v-model="newHash" placeholder="选择对比版本" style="width: 260px" filterable>
        <el-option v-for="h in history" :key="h.full_hash"
          :label="`${new Date(h.date).toLocaleString('zh-CN')} — ${h.hash}`"
          :value="h.full_hash" />
      </el-select>
    </div>

    <div class="compare-body" v-loading="loading">
      <div v-if="oldHash && newHash && diffText" class="diff-view">
        <CodeDiffView :diff="diffText" :old-text="oldText" :new-text="newText" />
      </div>
      <div v-else-if="oldHash && newHash && !loading" class="diff-empty">两个版本相同，无变更</div>
      <div v-else class="diff-empty">请选择两个版本进行对比</div>
    </div>
  </el-dialog>
</template>

<style scoped>
.compare-selectors {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 8px;
}
.arrow {
  font-size: 16px;
  color: #909399;
}
.compare-body {
  height: 65vh;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overflow: hidden;
}
.diff-view {
  height: 100%;
  overflow: auto;
}
.diff-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #909399;
}
</style>
