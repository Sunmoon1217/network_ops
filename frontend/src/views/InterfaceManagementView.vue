<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import api from '../utils/django_api'
import type { TableColumn } from '@/types'
import type { InterfaceConfig } from '../types'
import type { ComponentSize } from 'element-plus'

const router = useRouter()
const interfaces = ref<InterfaceConfig[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

// 分页相关变量
const currentPage = ref(1)
const pageSize = ref(15)
const totalItems = ref(0)
const totalPages = ref(0)
const size = ref<ComponentSize>('default')
const emit = defineEmits<{
  'page-change': [page: number]
  'size-change': [size: number]
  'refresh': []
}>()

// 搜索和过滤相关变量
const searchQuery = ref('')
const statusFilter = ref('all')
const deviceFilter = ref('all')
const ipFilter = ref('')

// 设备列表（用于过滤器）
const devices = ref<{ id: number; name: string }[]>([])

// 状态选项
const statusOptions = [
  { value: 'all', label: '全部状态' },
  { value: 'up', label: '启用' },
  { value: 'down', label: '禁用' },
  { value: 'admin_down', label: '管理关闭' },
]

// 获取设备列表（用于过滤器）
async function fetchDevices() {
  try {
    console.log('获取设备列表 - 发送请求')
    const data = await api.get('/devices/')
    console.log('获取设备列表 - 响应:', data)
    devices.value =
      data.data?.results?.map((device: any) => ({
        id: device.id,
        name: device.hostname,
      })) || []
  } catch (e) {
    console.error('获取设备列表失败:', e)
  }
}

// 定义表格列
const columns = ref<TableColumn[]>([
  {
    prop: 'device_name',
    label: '设备名称',
    width: 230,
    sortable: true,
    formatter: (row: any) => {
      return `<span class="clickable" @click="goToDeviceDetails(${row.device_id})"><i class="el-icon-view"></i> ${row.device_name || '-'}</span>`
    }
  },
  {
    prop: 'interface',
    label: '接口名称',
    width: 200,
    sortable: true
  },
  {
    prop: 'description',
    label: '接口描述',
    minWidth: 200,
    showOverflowTooltip: true
  },
  {
    prop: 'vrf',
    label: 'VPN实例',
    width: 150,
    sortable: true
  },
  {
    prop: 'if_address',
    label: '接口地址',
    width: 180,
    sortable: true
  },
  { prop: 'shutdown',
    label: '状态',
    width: 120, 
    sortable: true, 
    formatter: (row: { shutdown?: boolean }) => { 
      return row.shutdown ? 'Shutdown' : 'UP' 
    } 
  }
])

// 获取接口配置
async function fetchInterfaces(page = 1) {
  loading.value = true
  error.value = null
  try {
    // 构建查询参数
    const params: any = {
      page: page,
      page_size: pageSize.value,
    }

    // 添加搜索参数
    if (searchQuery.value) {
      params.search = searchQuery.value
    }

    // 添加状态过滤
    if (statusFilter.value !== 'all') {
      params.status = statusFilter.value
    }

    // 添加设备过滤
    if (deviceFilter.value !== 'all') {
      params.device = deviceFilter.value
    }

    // 添加IP过滤
    if (ipFilter.value) {
      params.ip_address = ipFilter.value
    }

    console.log('发送API请求:', {
      url: '/interfaces/',
      params: params,
      baseURL: import.meta.env.VITE_API_BASE_URL,
    })

    // 发送请求
    const data = await api.get('/interfaces/', { params })

    console.log('API响应:', data)

    // 处理响应数据
    interfaces.value = data.data?.results || []
    totalItems.value = data.data?.count || 0
    // 不再需要计算总页数，DataTable会自动处理
    totalPages.value = Math.ceil(totalItems.value / pageSize.value)
    currentPage.value = page
  } catch (e) {
    console.error('API请求失败:', e)
    error.value = e instanceof Error ? e.message : '获取接口配置失败'
  } finally {
    loading.value = false
  }
}

// 重置所有过滤器
function resetFilters() {
  searchQuery.value = ''
  statusFilter.value = 'all'
  deviceFilter.value = 'all'
  ipFilter.value = ''
  fetchInterfaces(1) // 重置后重新获取数据，回到第一页
}

// 应用过滤器（分页回到第一页）
function applyFilters() {
  fetchInterfaces(1)
}

// 分页变化处理
function handlePageChange(page: number) {
  currentPage.value = page
  console.log('当前页面：', page)
  fetchInterfaces(page)
}

function handleSizeChange(size: number) {
  pageSize.value = size
  fetchInterfaces(1) // 回到第一页
}

const handleCurrentChange = (page: number) => {
  currentPage.value = page
  fetchInterfaces(page)
}
// 跳转到设备详情
function goToDeviceDetails(deviceId: number) {
  router.push(`/devices/${deviceId}/config`)
}

// 组件挂载时初始化数据
onMounted(async () => {
  console.log('组件挂载 - 开始初始化数据')
  await fetchDevices()
  console.log('组件挂载 - 设备列表获取完成，开始获取接口数据')
  await fetchInterfaces()
  console.log('组件挂载 - 接口数据获取完成')
  console.log('组件挂载 - 接口数据:', interfaces.value)
})
</script>

<template>
  <div class="interface-management-container">
    <h2 class="viewtitle">接口管理</h2>

    <!-- 搜索和过滤区域 -->
    <div class="filters-container">
      <div class="filter-row">
        <!-- 搜索框 -->
        <div class="filter-item">
          <label for="search">搜索:</label>
          <input
            id="search"
            v-model="searchQuery"
            type="text"
            placeholder="搜索接口名称、描述..."
            @keyup.enter="applyFilters"
          />
        </div>

        <!-- 状态过滤器 -->
        <div class="filter-item">
          <label for="status">状态:</label>
          <select id="status" v-model="statusFilter">
            <option v-for="option in statusOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </div>

        <!-- 设备过滤器 -->
        <div class="filter-item">
          <label for="device">设备:</label>
          <select id="device" v-model="deviceFilter">
            <option value="all">所有设备</option>
            <option v-for="device in devices" :key="device.id" :value="device.id">
              {{ device.name }}
            </option>
          </select>
        </div>

        <!-- IP地址过滤器 -->
        <div class="filter-item">
          <label for="ip">IP地址:</label>
          <input
            id="ip"
            v-model="ipFilter"
            type="text"
            placeholder="例如: 192.168.1."
            @keyup.enter="applyFilters"
          />
        </div>

        <!-- 按钮组 -->
        <div class="filter-buttons">
          <button @click="applyFilters" class="apply-btn">应用过滤器</button>
          <button @click="resetFilters" class="reset-btn">重置</button>
        </div>
      </div>
    </div>

    <!-- 数据加载状态 -->
    <div v-if="loading" class="loading">
      <p>加载中...</p>
    </div>

    <!-- 错误信息 -->
    <div v-else-if="error" class="error">
      <p>错误: {{ error }}</p>
      <button @click="fetchInterfaces(currentPage)" class="retry-btn">重试</button>
    </div>

    <!-- 接口表格 -->
    <div v-else class="interface-table-container">
      <el-table
        :data="interfaces"
        class="interface-table"
      >
        <el-table-column 
          v-for="col in columns"
          :prop="col.prop"
          :label="col.label"
          :width="col.width"
        />
      </el-table>
      <el-pagination
        style="height: 10%;"
        :current-page="currentPage"
        @update:current-page="handleCurrentChange"
        :page-sizes="[15, 30, 50, 100]"
        background
        :size="size"
        layout="->, total, jumper, prev, pager, next, sizes"
        :total="totalItems"
      />
    </div>
  </div>
</template>

<style scoped>
.interface-management-container {
  max-width: 100%;
  margin: 0 auto;
  padding: 10px;
  height: 100%;
  display: flex;
  flex-direction: column;
}
.viewtitle{
  flex: 3;
}
/* 搜索和过滤区域样式 */
.filters-container {
  flex: 6;
  background-color: #f8f9fa;
  border-radius: 8px;
  padding: 6px;
  margin-bottom: 6px;
  box-shadow: 1px 2px 4px rgba(0, 0, 0, 0.1);
}

.filter-row {
  display: flex;
  flex-wrap: wrap-reverse;
  gap: 5px;
  align-items:center;
}

.filter-item {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 150px;
}

.filter-item label {
  font-weight: bold;
  font-size: 14px;
  color: #333;
}

.filter-item input,
.filter-item select {
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
}

.filter-buttons {
  display: flex;
  gap: 10px;
  margin-left: auto;
}

.apply-btn {
  background-color: #409eff;
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: background-color 0.3s;
}

.apply-btn:hover {
  background-color: #66b1ff;
}

.reset-btn {
  background-color: #909399;
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: background-color 0.3s;
}

.reset-btn:hover {
  background-color: #a6a9ad;
}

/* 表格样式 */
.interface-table-container {
  flex: 41;
  position: relative;
  height: 100%;
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.interface-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
  overflow-x: auto;
}

.interface-table th {
  background-color: #f5f7fa;
  padding: 12px;
  text-align: left;
  font-weight: bold;
  color: #303133;
  border-bottom: 1px solid #e4e7ed;
}

.interface-table td {
  padding: 12px;
  border-bottom: 1px solid #ebeef5;
}

.interface-table tr:hover {
  background-color: #f5f7fa;
}

.table-pagination {
  flex: 1;
  /* padding: 16px; */
  border-top: 1px solid #ebeef5;
  display: flex;
  justify-content: flex-end;
}

.clickable {
  color: #409eff;
  cursor: pointer;
}

.clickable:hover {
  text-decoration: underline;
}

/* 状态徽章样式 */
.status-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: bold;
}

/* 红色状态样式 */
.status-red {
  color: #f56c6c;
  font-weight: bold;
}

.status-up {
  background-color: #f0f9eb;
  color: #67c23a;
  border: 1px solid #c2e7b0;
}

.status-down {
  background-color: #fef0f0;
  color: #f56c6c;
  border: 1px solid #fbc4c4;
}

.status-admin {
  background-color: #f0f0f0;
  color: #909399;
  border: 1px solid #d9d9d9;
}

/* 操作按钮样式 */
.view-btn {
  background-color: #67c23a;
  color: white;
  border: none;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: background-color 0.3s;
}

.view-btn:hover {
  background-color: #85ce61;
}

/* 加载和错误状态样式 */
.loading,
.error,
.no-data {
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

.retry-btn {
  background-color: #3498db;
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
  margin-top: 10px;
}

.retry-btn:hover {
  background-color: #2980b9;
}

.no-data {
  background-color: #f9f9f9;
  border: 1px solid #e0e0e0;
  color: #7f8c8d;
}
</style>
