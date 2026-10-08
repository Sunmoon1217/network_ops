<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import CodeDiffView from '@/components/CodeDiffView.vue'
import { getDevice, getGitConfigContent, getGitDiff } from '@/api/devices'

const route = useRoute()
const router = useRouter()
const deviceId = Number(route.params.id)

const device = ref<any>(null)
const diffText = ref('')
const oldText = ref('')
const newText = ref('')
const oldHash = ref('')
const newHash = ref('')
const loading = ref(true)

const fetchDiff = async () => {
  loading.value = true
  oldHash.value = (route.query.old as string) || ''
  newHash.value = (route.query.new as string) || ''

  if (!oldHash.value || !newHash.value) {
    loading.value = false
    return
  }

  try {
    const deviceRes = await getDevice(deviceId)
    device.value = deviceRes.data
    const hostname = device.value.hostname

    // 全文喂组件显示完整配置；后端 diff 只用来判空态（unified diff 只带变更±3行）
    const [oldRes, newRes, diffRes] = await Promise.all([
      getGitConfigContent(hostname, oldHash.value),
      getGitConfigContent(hostname, newHash.value),
      getGitDiff(hostname, oldHash.value, newHash.value),
    ])
    oldText.value = oldRes.data.config_text || ''
    newText.value = newRes.data.config_text || ''
    diffText.value = diffRes.data.diff || ''
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(fetchDiff)
</script>

<template>
  <div class="compare-page">
    <div class="page-header">
      <el-button text @click="router.back()">← 返回</el-button>
      <h2>配置对比 — {{ device?.hostname || '...' }}</h2>
    </div>

    <div class="compare-info" v-if="oldHash && newHash">
      <span>基准: <code>{{ oldHash.slice(0, 8) }}</code></span>
      <span>→</span>
      <span>对比: <code>{{ newHash.slice(0, 8) }}</code></span>
    </div>

    <div v-if="loading" v-loading="true" class="compare-body" />
    <div v-else-if="oldHash && newHash && diffText" class="compare-body">
      <CodeDiffView :diff="diffText" :old-text="oldText" :new-text="newText" />
    </div>
    <el-empty v-else description="缺少对比参数或无变更" class="compare-body" />
  </div>
</template>

<style scoped>
.compare-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 20px;
}
.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-shrink: 0;
}
.page-header h2 {
  margin: 0;
  font-size: 1.2rem;
  font-weight: 600;
}
.compare-info {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  background: #fff;
  border-radius: 8px;
  margin-bottom: 12px;
  font-size: 13px;
  color: #606266;
  flex-shrink: 0;
}
.compare-info code {
  background: #f5f7fa;
  padding: 2px 8px;
  border-radius: 4px;
  font-family: monospace;
}
.compare-body {
  flex: 1;
  min-height: 0;
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
}
</style>
