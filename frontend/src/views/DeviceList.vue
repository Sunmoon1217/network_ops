<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../utils/django_api'
import Pagination from '../components/Pagination.vue'
import type { Device } from '../types'

const router = useRouter()
const devices = ref<Device[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

// 分页相关变量
const currentPage = ref(1)
const pageSize = ref(10)
const totalItems = ref(0)
const totalPages = ref(1)

async function fetchDevices(page = 1) {
  loading.value = true
  error.value = null
  try {
    // 发送带有分页参数的请求
    const data = await api.get('/devices/', {
      params: {
        page: page,
        page_size: pageSize.value,
      },
    })

    // 假设后端返回的数据格式包含results和分页信息
    // 示例: { "count": 100, "next": "...", "previous": "...", "results": [...] }
    devices.value = data.data?.results || []
    totalItems.value = data.data?.count || 0
    totalPages.value = Math.ceil(totalItems.value / pageSize.value)
    currentPage.value = page
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Unknown error'
  } finally {
    loading.value = false
  }
}



// 页码变化处理
function handlePageChange(page: number) {
  fetchDevices(page)
}

onMounted(() => {
  fetchDevices()
})
</script>

<template>
  <div class="device-list-container">
    <div class="device-list-header">
      <h2>设备管理</h2>
      <button class="add-device-btn" @click="router.push('/devices/create')">添加设备</button>
    </div>

    <div v-if="loading" class="loading">
      <p>加载中...</p>
    </div>

    <div v-else-if="error" class="error">
      <p>错误: {{ error }}</p>
      <button @click="fetchDevices(currentPage)">重试</button>
    </div>

    <div v-else class="device-table-container">
      <table class="device-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>主机名</th>
            <th>IP地址</th>
            <th>用户名</th>
            <th>设备类型</th>
            <th>连接失败时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="device in devices" :key="device.id">
            <td>{{ device.id }}</td>
            <td>{{ device.hostname }}</td>
            <td>{{ device.address }}</td>
            <td>{{ device.username }}</td>
            <td>{{ device.device_type }}</td>
            <td>{{ device.connect_failed_at || '-' }}</td>
            <td>
              <button class="config-btn" @click="router.push(`/devices/${device.id}/config`)">
                查看配置
              </button>
              <button class="history-btn" @click="router.push(`/devices/${device.id}/history`)">
                历史配置
              </button>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- 分页组件 -->
      <Pagination
        v-if="totalItems > 0"
        :current-page="currentPage"
        :total-pages="totalPages"
        :page-size="pageSize"
        :total-items="totalItems"
        :on-page-change="handlePageChange"
      />
    </div>
  </div>
</template>

<style scoped>
.device-list-container {
  max-width: 100%;
  margin: 0 auto;
  padding: 20px;
}

h2 {
  color: #2c3e50;
  margin-bottom: 20px;
}

.device-list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.add-device-btn {
  background-color: #409eff;
  color: #fff;
  border: none;
  padding: 8px 14px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.95rem;
}

.add-device-btn:hover {
  background-color: #66b1ff;
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

.device-table-container {
  overflow-x: auto;
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  padding: 20px;
}

.device-table {
  width: 100%;
  border-collapse: collapse;
}

.device-table th,
.device-table td {
  padding: 12px 15px;
  text-align: left;
  border-bottom: 1px solid #ecf0f1;
}

.device-table th {
  background-color: #f5f7fa;
  font-weight: bold;
  color: #2c3e50;
}

.device-table tr:hover {
  background-color: #f5f7fa;
}

.device-count {
  margin-top: 20px;
  text-align: right;
  color: #7f8c8d;
  font-size: 0.9rem;
}

.config-btn,
.history-btn {
  padding: 6px 12px;
  margin-right: 8px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85rem;
  transition: background-color 0.3s;
}

.config-btn {
  background-color: #409eff;
  color: white;
}

.config-btn:hover {
  background-color: #66b1ff;
}

.history-btn {
  background-color: #67c23a;
  color: white;
}

.history-btn:hover {
  background-color: #85ce61;
}
</style>
