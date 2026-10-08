<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { getDevice, getDeviceConfigs, getGitConfigContent } from '@/api/devices'

const route = useRoute()
const router = useRouter()
const deviceId = Number(route.params.id)

const device = ref<any>(null)
const configContent = ref<string>('')
const configMeta = ref<any>(null)
const loading = ref(true)

const fetchLatestConfig = async () => {
  loading.value = true
  try {
    const deviceRes = await getDevice(deviceId)
    device.value = deviceRes.data

    const configsRes = await getDeviceConfigs({ device: deviceId })
    const configs = configsRes.data.results || configsRes.data || []

    if (configs.length > 0) {
      const latest = configs[0]
      configMeta.value = latest
      try {
        const contentRes = await getGitConfigContent(device.value.hostname, latest.git_commit_hash)
        configContent.value = contentRes.data.config_text || ''
      } catch {
        configContent.value = JSON.stringify(latest.config_json, null, 2) || ''
      }
    }
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

const goToHistory = () => {
  router.push(`/devices/${deviceId}/history`)
}

onMounted(fetchLatestConfig)
</script>

<template>
  <div class="config-page">
    <div class="page-header">
      <el-button text @click="router.back()">← 返回</el-button>
      <h2>设备配置 — {{ device?.hostname || '...' }}</h2>
      <div class="header-actions">
        <el-button @click="fetchLatestConfig" :loading="loading">刷新</el-button>
        <el-button type="primary" @click="goToHistory">查看历史</el-button>
      </div>
    </div>

    <div v-if="loading" v-loading="true" class="config-body" />
    <div v-else-if="configContent" class="config-body">
      <div class="config-meta" v-if="configMeta">
        <span>Commit: {{ configMeta.git_commit_hash?.slice(0, 8) }}</span>
        <span>采集时间: {{ new Date(configMeta.collected_at).toLocaleString('zh-CN') }}</span>
      </div>
      <pre class="config-text">{{ configContent }}</pre>
    </div>
    <el-empty v-else description="暂无配置记录" class="config-body" />
  </div>
</template>

<style scoped>
.config-page {
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
.header-actions {
  display: flex;
  gap: 8px;
}
.config-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
}
.config-meta {
  display: flex;
  gap: 16px;
  padding: 12px 16px;
  font-size: 13px;
  color: #909399;
  border-bottom: 1px solid #ebeef5;
  flex-shrink: 0;
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
