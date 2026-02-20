<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import type { WideipConfig } from '@/types/wideip'
import type { TableColumn, TablePagination } from '@/types'

// 数据类型
const wideips = ref<WideipConfig[]>([])

// 数据状态
const loading = ref(false)
const error = ref<string | null>(null)

// 分页变量
const currentPage = ref(1)
const pageSize = ref(15)
const totalItems = ref(0)

// 分页计算
const pagination = computed<TablePagination>(() => ({
    currentPage: currentPage.value,
    pageSize: pageSize.value,
    total: totalItems.value,
    pageSizes: [15, 30, 50, 100],
    layout: 'total, sizes, prev, pager, next, jumper'
}))

// 搜索和过滤
const searchQuery = ref('')
const statusFilter = ref('all')
const deviceFilter = ref('all')
const ipFilter = ref('')

// 设备列表
const devices = ref<{ id: number; name: string }[]>([])

// 定义表格列
const columns = ref<TableColumn[]>([
    {
        prop: 'device_name',
        label: '设备名称'
    },
    {
        prop: 'wideip',
        label: '域名'
    },
    {
        prop: 'type',
        label: '类型'
    },
])


// 模拟数据
const wideipdata = ref<WideipConfig[]>([
    { id: 1, device_id: 12, device_name: 'switch', wideip: 'www.baidu.com', type: 'A' },
    { id: 2, device_id: 12, device_name: 'switch', wideip: 'www.baidu2.com', type: 'A' }
])

// 分页处理
function handlePageChange(page: number) {
    currentPage.value = page
    return 0
}
function handleSizeChange(size: number) {
    pageSize.value = size
    return 0
}

</script>

<template>
    <div class="main-container">
        <div class="viewtitle">
            <h2>DNS</h2>
        </div>
        <div class="filter">filter</div>
        <div v-if="loading">
            <p>加载中。。。</p>
        </div>
        <div v-else-if="error">
            <p>错误信息： {{ error }}</p>
        </div>
        <div v-else class="data">
                <el-table :data="wideipdata" class="table">
                    <el-table-column prop="id" label="ID" />
                    <el-table-column prop="device_id" label="设备ID" />
                    <el-table-column prop="device_name" label="设备" />
                    <el-table-column prop="wideip" label="域名" />
                    <el-table-column prop="type" label="类型" />
                </el-table>
        <div class="pagination">pagination</div>
        </div>
    </div>
</template>

<style scoped>
.main-container {
    height: 100%;
    width: 100%;
    display: flex;
    flex-direction: column;
    margin: 2px;
}

.viewtitle {
    flex: 2;
}

.filter {
    flex: 6;
    padding: 10px;
    box-sizing: border-box;
    background-color: #bcd5ed;
    border-radius: 8px;
    box-shadow: 2px 2px 4px rgba(0, 0, 0, 0.1);
}

.data {
    flex: 40;
    margin: 2px;
    border: 1px solid black;
    display: flex;
    flex-direction: column;
}

.table{
    flex: 15;
}
.pagination {
    flex: 1;
}
</style>