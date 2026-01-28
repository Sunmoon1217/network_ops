<script setup lang="ts">
import { computed } from 'vue'

// 分页组件接口定义
interface PaginationProps {
  currentPage: number
  totalPages: number
  pageSize: number
  totalItems: number
  onPageChange: (page: number) => void
}

// 接收父组件传递的参数
const props = withDefaults(defineProps<PaginationProps>(), {
  currentPage: 1,
  totalPages: 1,
  pageSize: 10,
  totalItems: 0,
  onPageChange: () => {},
})

// 计算当前页的显示范围
const getDisplayRange = () => {
  const start = (props.currentPage - 1) * props.pageSize + 1
  const end = Math.min(start + props.pageSize - 1, props.totalItems)
  return { start, end }
}

// 生成页码数组
const getPageNumbers = () => {
  const pages: (number | string)[] = []
  const maxVisiblePages = 5

  // 如果总页数小于等于最大可见页数，显示所有页码
  if (props.totalPages <= maxVisiblePages) {
    for (let i = 1; i <= props.totalPages; i++) {
      pages.push(i)
    }
  } else {
    // 显示当前页前后的页码
    const halfVisible = Math.floor(maxVisiblePages / 2)
    let startPage = Math.max(1, props.currentPage - halfVisible)
    let endPage = Math.min(props.totalPages, startPage + maxVisiblePages - 1)

    // 调整起始页，确保显示足够的页码
    if (endPage - startPage + 1 < maxVisiblePages) {
      startPage = Math.max(1, endPage - maxVisiblePages + 1)
    }

    // 添加省略号
    if (startPage > 1) {
      pages.push(1)
      if (startPage > 2) {
        pages.push('...')
      }
    }

    // 添加页码
    for (let i = startPage; i <= endPage; i++) {
      pages.push(i)
    }

    // 添加省略号
    if (endPage < props.totalPages) {
      if (endPage < props.totalPages - 1) {
        pages.push('...')
      }
      pages.push(props.totalPages)
    }
  }

  return pages
}

// 页码数组
const pageNumbers = computed(() => getPageNumbers())

// 显示范围
const displayRange = computed(() => getDisplayRange())

// 上一页
const goToPrevPage = () => {
  if (props.currentPage > 1) {
    props.onPageChange(props.currentPage - 1)
  }
}

// 下一页
const goToNextPage = () => {
  if (props.currentPage < props.totalPages) {
    props.onPageChange(props.currentPage + 1)
  }
}

// 跳转到指定页码
const goToPage = (page: number | string) => {
  // 确保page是数字类型
  if (typeof page === 'number' && page >= 1 && page <= props.totalPages && page !== props.currentPage) {
    props.onPageChange(page)
  }
}
</script>

<template>
  <div class="pagination-container">
    <div class="pagination-info">
      <span>显示 {{ displayRange.start }} - {{ displayRange.end }} 条，共 {{ totalItems }} 条</span>
    </div>

    <div class="pagination-controls">
      <button class="page-btn" :disabled="currentPage === 1" @click="goToPrevPage">上一页</button>

      <div class="page-numbers">
        <button
          v-for="(page, index) in pageNumbers"
          :key="index"
          class="page-btn"
          :class="{
            'current-page': typeof page === 'number' && page === currentPage,
            ellipsis: page === '...',
          }"
          :disabled="page === '...'"
          @click="goToPage(page)"
        >
          {{ page }}
        </button>
      </div>

      <button class="page-btn" :disabled="currentPage === totalPages" @click="goToNextPage">
        下一页
      </button>
    </div>
  </div>
</template>

<style scoped>
.pagination-container {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 20px;
  padding: 10px 0;
  border-top: 1px solid #ecf0f1;
}

.pagination-info {
  color: #7f8c8d;
  font-size: 0.9rem;
}

.pagination-controls {
  display: flex;
  align-items: center;
  gap: 10px;
}

.page-btn {
  padding: 6px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  background-color: white;
  color: #606266;
  cursor: pointer;
  font-size: 0.9rem;
  transition: all 0.3s;
}

.page-btn:hover:not(:disabled) {
  border-color: #409eff;
  color: #409eff;
}

.page-btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
  border-color: #dcdfe6;
  color: #c0c4cc;
}

.current-page {
  background-color: #409eff;
  border-color: #409eff;
  color: white;
}

.current-page:hover {
  background-color: #66b1ff;
  border-color: #66b1ff;
  color: white;
}

.ellipsis {
  cursor: default;
  border: none;
  padding: 6px 4px;
}

.ellipsis:hover {
  border: none;
  color: #606266;
}

.page-numbers {
  display: flex;
  gap: 4px;
}
</style>
