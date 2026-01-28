<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '@/utils/django_api'

interface ApiResponse {
  message: string
  status: string
  service: string
  version: string
}

const apiData = ref<ApiResponse | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

async function fetchData() {
  loading.value = true
  error.value = null
  try {
    // 使用根路径获取首页数据
    const response = await api.get('index/')
    apiData.value = response.data || {}
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Unknown error'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchData()
})
</script>

<template>
  <div class="welcome-container">
    <h1>网络运维平台</h1>
    <!-- 1 2 3 -->
    <div v-if="loading" class="loading">
      <p>加载中...</p>
    </div>

    <div v-else-if="error" class="error">
      <p>错误: {{ error }}</p>
      <button @click="fetchData">重试</button>
    </div>

    <div v-else-if="apiData" class="api-data">
      <div class="card">
        <h2>{{ apiData.message }}</h2>
        <p><strong>状态:</strong> {{ apiData.status }}</p>
        <p><strong>服务:</strong> {{ apiData.service }}</p>
        <p><strong>版本:</strong> {{ apiData.version }}</p>
      </div>
      <button @click="fetchData" class="refresh-btn">刷新数据</button>
    </div>
  </div>
</template>

<style scoped>
.welcome-container {
  max-width: 800px;
  margin: 0 auto;
  padding: 20px;
  font-family: Arial, sans-serif;
}

h1 {
  color: #333;
  text-align: center;
}

.loading,
.error,
.api-data {
  margin: 20px 0;
  padding: 20px;
  border-radius: 8px;
}

.loading {
  background-color: #f0f8ff;
  border: 1px solid #add8e6;
  text-align: center;
}

.error {
  background-color: #ffebee;
  border: 1px solid #ffcdd2;
  color: #c62828;
}

.api-data {
  background-color: #f3f4f6;
}

.card {
  background-color: white;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  margin-bottom: 20px;
}

.card h2 {
  margin-top: 0;
  color: #2c3e50;
}

.card p {
  margin: 10px 0;
  color: #555;
}

.refresh-btn {
  background-color: #3498db;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 16px;
}

.refresh-btn:hover {
  background-color: #2980b9;
}
</style>
