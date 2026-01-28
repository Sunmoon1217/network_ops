<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../utils/django_api'
import Pagination from '../components/Pagination.vue'
import type { Config } from '../types'

const route = useRoute()
const router = useRouter()
const deviceId = ref<number | null>(null)
const deviceName = ref<string>('')
const configs = ref<Config[]>([])
const selectedConfig = ref<Config | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

// 分页相关变量
const currentPage = ref(1)
const pageSize = ref(10)
const totalItems = ref(0)
const totalPages = ref(1)

// 返回上一个页面
function goBack() {
  if (router.options.history.state.back) {
    router.back()
  } else {
    // 如果没有历史记录，默认返回设备配置页面
    router.push(`/devices/${deviceId.value}/config`)
  }
}

async function fetchConfigs(page = 1) {
  loading.value = true
  error.value = null
  try {
    // 获取设备信息
    const deviceData = await api.get(`/devices/${deviceId.value}/`)
    deviceName.value = deviceData.data?.hostname || ''

    // 获取所有配置（带分页）
    const configData = await api.get(`/configs/?device=${deviceId.value}&ordering=-time`, {
      params: {
        page: page,
        page_size: pageSize.value,
      },
    })

    // 假设后端返回的数据格式包含results和分页信息
    configs.value = configData.data?.results || []
    totalItems.value = configData.data.count || 0
    totalPages.value = Math.ceil(totalItems.value / pageSize.value)
    currentPage.value = page

    // 默认选择最新的配置
    if (configs.value.length > 0) {
      selectedConfig.value = configs.value[0] || null
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Unknown error'
  } finally {
    loading.value = false
  }
}

// 页码变化处理
function handlePageChange(page: number) {
  fetchConfigs(page)
}

function selectConfig(config: Config) {
  selectedConfig.value = config
}

onMounted(() => {
  const id = route.params.id
  if (typeof id === 'string') {
    deviceId.value = parseInt(id)
    fetchConfigs()
  }
})
</script>

<template>
  <div class="history-container">
    <h2>设备历史配置</h2>

    <div v-if="loading" class="loading">
      <p>加载中...</p>
    </div>

    <div v-else-if="error" class="error">
      <p>错误: {{ error }}</p>
      <button @click="fetchConfigs(currentPage)">重试</button>
    </div>

    <div v-else class="history-content">
      <div class="device-header">
        <h3>设备: {{ deviceName }}</h3>
        <div class="header-actions">
          <button @click="goBack" class="back-btn">返回</button>
        </div>
      </div>

      <div class="history-wrapper">
        <div class="config-list">
          <h4>配置历史</h4>
          <div v-if="configs.length === 0" class="no-configs">
            <p>该设备暂无配置记录</p>
          </div>
          <ul v-else class="config-items">
            <li
              v-for="config in configs"
              :key="config.id"
              class="config-item"
              :class="{ active: selectedConfig?.id === config.id }"
              @click="selectConfig(config)"
            >
              <div class="config-time">{{ new Date(config.time).toLocaleString() }}</div>
              <div class="config-id">#{{ config.id }}</div>
            </li>
          </ul>

          <!-- 分页组件 -->
          <div v-if="totalItems > 0" class="pagination-container">
            <Pagination
              :current-page="currentPage"
              :total-pages="totalPages"
              :page-size="pageSize"
              :total-items="totalItems"
              :on-page-change="handlePageChange"
            />
          </div>
        </div>

        <div class="config-detail">
          <div v-if="selectedConfig" class="detail-content">
            <div class="detail-header">
              <h4>配置详情</h4>
              <div class="detail-meta">
                <span>配置ID: {{ selectedConfig.id }}</span>
                <span>保存时间: {{ new Date(selectedConfig.time).toLocaleString() }}</span>
              </div>
            </div>
            <pre class="config-text">{{ selectedConfig.config_text }}</pre>
          </div>
          <div v-else class="no-selected">
            <p>请选择一个配置查看详情</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.history-container {
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

.device-header h3 {
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 10px;
}

.back-btn {
  background-color: #95a5a6;
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: background-color 0.3s;
}

.back-btn:hover {
  background-color: #7f8c8d;
}

.history-wrapper {
  display: flex;
  gap: 20px;
  height: 70vh;
}

.config-list {
  width: 300px;
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  display: flex;
  flex-direction: column;
}

.config-list h4 {
  padding: 15px 20px;
  margin: 0;
  border-bottom: 1px solid #e0e0e0;
  font-size: 16px;
}

.config-items {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  flex: 1;
}

.pagination-container {
  padding: 15px;
  border-top: 1px solid #e0e0e0;
}

.config-item {
  padding: 15px 20px;
  cursor: pointer;
  border-bottom: 1px solid #f0f0f0;
  transition: background-color 0.3s;
}

.config-item:hover {
  background-color: #f5f7fa;
}

.config-item.active {
  background-color: #e3f2fd;
  border-left: 4px solid #2196f3;
}

.config-time {
  font-size: 14px;
  color: #333;
  margin-bottom: 5px;
}

.config-id {
  font-size: 12px;
  color: #7f8c8d;
}

.no-configs {
  padding: 20px;
  text-align: center;
  color: #7f8c8d;
}

.config-detail {
  flex: 1;
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  display: flex;
  flex-direction: column;
}

.detail-content {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.detail-header {
  padding: 15px 20px;
  border-bottom: 1px solid #e0e0e0;
}

.detail-header h4 {
  margin: 0 0 10px 0;
  font-size: 16px;
}

.detail-meta {
  display: flex;
  gap: 20px;
  font-size: 14px;
  color: #7f8c8d;
}

.config-text {
  flex: 1;
  background-color: #f5f5f5;
  border-radius: 0 0 8px 8px;
  padding: 15px;
  white-space: pre-wrap;
  font-family: 'Courier New', Courier, monospace;
  font-size: 14px;
  line-height: 1.5;
  overflow-y: auto;
  border: 1px solid #e0e0e0;
  margin: 0;
}

.no-selected {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
  color: #7f8c8d;
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
