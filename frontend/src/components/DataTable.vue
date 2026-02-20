<script setup lang="ts">
import { ref, computed } from 'vue'
import type { TableColumn, TablePagination } from '@/types'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

interface Props {
  data: any[]
  columns: TableColumn[]
  loading?: boolean
  pagination?: TablePagination
  showPagination?: boolean
  stripe?: boolean
  border?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  data: () => [],
  columns: () => [],
  loading: false,
  showPagination: true,
  stripe: true,
  border: true,
  pagination: () => ({
    currentPage: 1,
    pageSize: 10,
    total: 0,
    pageSizes: [10, 20, 50, 100],
    layout: 'total, sizes, prev, pager, next, jumper'
  })
})

const emit = defineEmits<{
  'page-change': [page: number]
  'size-change': [size: number]
  'refresh': []
}>()

// 分页相关
const currentPage = ref(props.pagination.currentPage || 1)
const pageSize = ref(props.pagination.pageSize || 10)
const pageTotal = ref(props.pagination.total || 0)

// 分页变化处理
const handleSizeChange = (size: number) => {
  pageSize.value = size
  emit('size-change', size)
}

const handleCurrentChange = (page: number) => {
  currentPage.value = page
  emit('page-change', page)
}

// 刷新处理
const handleRefresh = () => {
  emit('refresh')
}

// 当前页数据计算
const currentPageData = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return props.data.slice(start, end)
})
</script>

<template>
  <div class="simple-data-table">
    <!-- 表格工具栏 -->
    <div v-if="$slots.toolbar" class="table-toolbar">
      <slot name="toolbar"></slot>
    </div>

    <!-- 数据表格 -->
    <div style="height: 60%;">
      <el-table :data="currentPageData" :stripe="stripe" :border="border" v-loading="loading" height="100%">
        <!-- 选择列 -->
        <el-table-column v-if="columns.some(col => col.type === 'selection')" type="selection" width="50" />

        <!-- 索引列 -->
        <el-table-column v-if="columns.some(col => col.type === 'index')" type="index" width="60" label="序号" />

        <!-- 数据列 -->
        <el-table-column
          v-for="column in columns.filter(col => !col.type || (col.type !== 'selection' && col.type !== 'index'))"
          :key="column.prop" :prop="column.prop" :label="column.label" :width="column.width"
          :min-width="column.minWidth" :sortable="column.sortable" :align="column.align"
          :show-overflow-tooltip="column.showOverflowTooltip">
          <template #default="scope">
            <!-- 自定义渲染 -->
            <template v-if="column.renderCell">
              <component :is="column.renderCell(scope)" />
            </template>

            <!-- 格式化渲染 -->
            <template v-else-if="column.formatter">
              <span v-html="column.formatter(scope.row, column, scope.row[column.prop], scope.$index)"></span>
            </template>

            <!-- 默认渲染 -->
            <template v-else>
              <span>{{ scope.row[column.prop] || '-' }}</span>
            </template>
          </template>
        </el-table-column>

        <!-- 操作列插槽 -->
        <el-table-column v-if="$slots.actions" label="操作" width="150" fixed="right">
          <template #default="scope">
            <slot name="actions" :row="scope.row" :index="scope.$index"></slot>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 分页组件 -->
    <el-config-provider :locale="zhCn">
      <div v-if="showPagination && pageTotal > 0" class="table-pagination">
        <el-pagination v-model:current-page="currentPage" v-model:page-size="pageSize"
          :page-sizes="pagination.pageSizes" :layout="pagination.layout" :total="pageTotal"
          @size-change="handleSizeChange" @current-change="handleCurrentChange" />
      </div>
    </el-config-provider>
  </div>
</template>

<style scoped>
.simple-data-table {
  width: 100%;
  background: #fff;
  border-radius: 4px;
}

.table-toolbar {
  padding: 16px;
  border-bottom: 1px solid #ebeef5;
}

.table-pagination {
  padding: 16px;
  border-top: 1px solid #ebeef5;
  display: flex;
  justify-content: flex-end;
}
</style>