<script setup lang="ts">
import { CodeDiff } from 'v-code-diff'
import { getGitConfigContent, getConfigHistory } from '@/api/devices'

const props = defineProps<{
  visible: boolean
  deviceId: number
  hostname: string
}>()
const emit = defineEmits<{ 'update:visible': [v: boolean] }>()

const history = ref<any[]>([])
const oldHash = ref('')
const newHash = ref('')
const oldText = ref('')
const newText = ref('')
const loading = ref(false)
const outputFormat = ref<'side-by-side' | 'line-by-line'>('side-by-side')

// 两段全文已在本地，直接比对即可判断有无变更（组件内部同口径）
const hasChange = computed(() => oldText.value !== newText.value)

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
    const [oldRes, newRes] = await Promise.all([
      getGitConfigContent(props.hostname, oldHash.value),
      getGitConfigContent(props.hostname, newHash.value),
    ])
    oldText.value = oldRes.data.config_text || ''
    newText.value = newRes.data.config_text || ''
  } catch {
    ElMessage.error('获取配置失败')
  } finally {
    loading.value = false
  }
}

const handleClose = () => {
  oldHash.value = ''
  newHash.value = ''
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
      <el-radio-group v-if="oldHash && newHash" v-model="outputFormat" size="small" class="format-toggle">
        <el-radio-button value="side-by-side">并排</el-radio-button>
        <el-radio-button value="line-by-line">行对行</el-radio-button>
      </el-radio-group>
    </div>

    <div class="compare-body" v-loading="loading">
      <div v-if="hasChange" class="diff-view">
        <CodeDiff
          :old-string="oldText"
          :new-string="newText"
          :output-format="outputFormat"
          :filename="oldHash.slice(0, 8)"
          :new-filename="newHash.slice(0, 8)"
        />
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
.format-toggle {
  margin-left: auto;
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
