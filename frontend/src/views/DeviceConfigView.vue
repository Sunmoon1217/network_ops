<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../utils/django_api'
import type { Config } from '../types'

const route = useRoute()
const router = useRouter()
const deviceId = ref<number | null>(null)
const deviceName = ref<string>('')
const latestConfig = ref<Config | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

// 保存进入当前页面时的上一个URL
const previousUrl = ref<string>('/devices')

// 返回上一个页面
function goBack() {
  if (router.options.history.state.back) {
    router.back()
  } else {
    // 如果没有历史记录，默认返回设备列表页面
    router.push(previousUrl.value)
  }
}

async function fetchLatestConfig() {
  loading.value = true
  error.value = null
  try {
    // 获取设备信息
    const deviceData = await api.get(`/devices/${deviceId.value}/`)
    deviceName.value = deviceData.data?.hostname || ''

    // 获取最新配置
    const configData = await api.get(`/devices/${deviceId.value}/config/`)

    // 后端返回的数据格式：{"success": true, "message": "...", "config": {...}}
    if (configData.data?.success && configData.data?.config) {
      latestConfig.value = configData.data?.config as Config
      latestConfig.value.id = deviceId.value || 0
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Unknown error'
  } finally {
    loading.value = false
  }
}

async function fetchConfigFromDevice() {
  console.log('开始获取设备配置...')
  console.log(`设备ID: ${deviceId.value}`)

  loading.value = true
  error.value = null
  try {
    // 调用API从设备获取配置
    console.log(`调用后端API: POST /devices/${deviceId.value}/fetch-config/`)
    const response = await api.post(`/devices/${deviceId.value}/fetch-config/`)
    console.log('API调用成功:', response)

    // 重新获取最新配置
    console.log('重新获取最新配置...')
    await fetchLatestConfig()
    console.log('获取配置完成')
  } catch (e) {
    console.error('获取配置失败:', e)
    error.value = e instanceof Error ? e.message : 'Unknown error'
  } finally {
    loading.value = false
  }
}

function goToHistory() {
  router.push(`/devices/${deviceId.value}/history`)
}

onMounted(() => {
  const id = route.params.id
  if (typeof id === 'string') {
    deviceId.value = parseInt(id)
    fetchLatestConfig()
  }

  // 记录进入时的上一个URL
  // 从导航状态中获取或设置默认值
  if (router.options.history.state.back) {
    // 如果有历史记录，使用router.back()会自动返回
    // 这里可以根据需要保存更具体的URL
  }
})
</script>

<template>
  <div class="config-container">
    <h2>设备配置管理</h2>

    <div v-if="loading" class="loading">
      <p>加载中...</p>
    </div>

    <div v-else-if="error" class="error">
      <p>错误: {{ error }}</p>
      <button @click="fetchLatestConfig">重试</button>
    </div>

    <div v-else class="config-content">
      <div class="device-header">
        <h3>设备: {{ deviceName }}</h3>
        <div class="header-actions">
          <button @click="goBack" class="back-btn">返回</button>
          <button @click="fetchConfigFromDevice" class="fetch-btn" :disabled="loading">
            获取配置
          </button>
          <button @click="goToHistory" class="history-btn">查看历史配置</button>
        </div>
      </div>

      <div class="config-section">
        <h4>最新配置</h4>
        <div class="config-meta">
          <span>保存时间: {{ latestConfig?.time }}</span>
        </div>
        <pre v-if="latestConfig" class="config-text">{{ latestConfig.config_text }}</pre>
        <div v-else class="no-config">
          <p>该设备暂无配置记录</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.config-container {
  max-width: 100%;
  margin: 0 auto;
  padding: 20px;
}

.device-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 10px;
  border-bottom: 1px solid #e0e0e0;
}

.header-actions {
  display: flex;
  gap: 10px;
}

.back-btn,
.history-btn,
.fetch-btn {
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: background-color 0.3s;
  margin-left: 10px;
}

.back-btn {
  background-color: #95a5a6;
}

.back-btn:hover {
  background-color: #7f8c8d;
}

.history-btn {
  background-color: #3498db;
}

.history-btn:hover {
  background-color: #2980b9;
}

.fetch-btn {
  background-color: #2ecc71;
}

.fetch-btn:hover {
  background-color: #27ae60;
}

.fetch-btn:disabled {
  background-color: #95a5a6;
  cursor: not-allowed;
}

.config-section {
  background-color: white;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.config-meta {
  color: #7f8c8d;
  margin-bottom: 15px;
  font-size: 0.9rem;
}

.config-text {
  background-color: #f5f5f5;
  border-radius: 4px;
  padding: 15px;
  white-space: pre-wrap;
  font-family: 'Courier New', Courier, monospace;
  font-size: 14px;
  line-height: 1.5;
  max-height: 600px;
  overflow-y: auto;
  border: 1px solid #e0e0e0;
}

.no-config {
  text-align: center;
  padding: 40px;
  color: #7f8c8d;
  background-color: #f9f9f9;
  border-radius: 4px;
}

.loading,
.error {
  margin: 20px 0;
  padding: 20px;
  border-radius: 8px;
  text-align: center;
}

.loading {
  background-color: #f0f8ff;
  border: 1px solid #add8e6;
}

.error {
  background-color: #ffebee;
  border: 1px solid #ffcdd2;
  color: #c62828;
}

.error button {
  background-color: #3498db;
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
  margin-top: 10px;
}

.error button:hover {
  background-color: #2980b9;
}
</style>
