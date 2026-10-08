<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { getDevice, getGitConfigContent, getConfigHistory } from '@/api/devices'
import CompareDialog from './dialogs/CompareDialog.vue'

const route = useRoute()
const router = useRouter()
const deviceId = Number(route.params.id)

const device = ref<any>(null)
const history = ref<any[]>([])
const selectedConfig = ref<any>(null)
const configContent = ref('')
const loading = ref(true)
const loadingContent = ref(false)
const compareVisible = ref(false)

const fetchHistory = async () => {
  loading.value = true
  try {
    const deviceRes = await getDevice(deviceId)
    device.value = deviceRes.data

    const historyRes = await getConfigHistory(device.value.hostname)
    history.value = historyRes.data.history || []

    if (history.value.length > 0) {
      await selectConfig(history.value[0])
    }
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

const selectConfig = async (config: any) => {
  selectedConfig.value = config
  loadingContent.value = true
  try {
    const res = await getGitConfigContent(device.value.hostname, config.full_hash)
    configContent.value = res.data.config_text || ''
  } catch {
    configContent.value = '加载失败'
  } finally {
    loadingContent.value = false
  }
}

onMounted(fetchHistory)
</script>

<template>
  <div class="history-page">
    <div class="page-header">
      <el-button text @click="router.back()">← 返回</el-button>
      <h2>历史配置 — {{ device?.hostname || '...' }}</h2>
      <el-button @click="compareVisible = true">对比</el-button>
    </div>

    <div v-if="loading" v-loading="true" class="history-body" />
    <div v-else class="history-body">
      <!-- 左侧列表 -->
      <div class="history-sidebar">
        <div class="sidebar-title">配置历史 ({{ history.length }})</div>
        <el-scrollbar>
          <div
            v-for="item in history"
            :key="item.full_hash"
            class="history-item"
            :class="{ active: selectedConfig?.full_hash === item.full_hash }"
            @click="selectConfig(item)"
          >
            <div class="item-time">{{ new Date(item.date).toLocaleString('zh-CN') }}</div>
            <div class="item-hash">{{ item.hash }}</div>
          </div>
        </el-scrollbar>
      </div>

      <!-- 右侧内容 -->
      <div class="history-content">
        <div class="content-header" v-if="selectedConfig">
          <span>Commit: {{ selectedConfig.hash }}</span>
          <span>{{ new Date(selectedConfig.date).toLocaleString('zh-CN') }}</span>
          <span>{{ selectedConfig.message }}</span>
        </div>
        <div v-if="loadingContent" v-loading="true" class="content-body" />
        <pre v-else class="config-text">{{ configContent || '选择配置查看详情' }}</pre>
      </div>
    </div>

    <CompareDialog
      v-model:visible="compareVisible"
      :device-id="deviceId"
      :hostname="device?.hostname || ''"
    />
  </div>
</template>

<style scoped>
.history-page {
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
  flex: 1;
}
.history-body {
  flex: 1;
  display: flex;
  gap: 16px;
  min-height: 0;
}
.history-sidebar {
  width: 260px;
  flex-shrink: 0;
  background: var(--el-bg-color);
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.sidebar-title {
  padding: 12px 16px;
  font-size: 14px;
  font-weight: 600;
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0;
}
.history-item {
  padding: 10px 16px;
  cursor: pointer;
  border-bottom: 1px solid var(--el-fill-color-light);
  transition: background 0.2s;
}
.history-item:hover {
  background: var(--el-fill-color-light);
}
.history-item.active {
  background: var(--el-color-primary-light-9);
  border-left: 3px solid var(--el-color-primary);
}
.item-time {
  font-size: 13px;
  color: var(--el-text-color-primary);
  margin-bottom: 2px;
}
.item-hash {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-family: monospace;
}
.history-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
  border-radius: 8px;
  overflow: hidden;
  min-width: 0;
}
.content-header {
  display: flex;
  gap: 16px;
  padding: 12px 16px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0;
}
.content-body {
  flex: 1;
}
.config-text {
  flex: 1;
  margin: 0;
  padding: 16px;
  overflow: auto;
  font-size: 13px;
  font-family: 'Courier New', monospace;
  line-height: 1.6;
  white-space: pre-wrap;
  background: var(--el-fill-color-light);
}
</style>
