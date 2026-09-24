<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  data: any[]
  loading?: boolean
  height?: string
  stripe?: boolean
  border?: boolean
  size?: 'large' | 'default' | 'small'
  // el-table 原生 row-key：字段名或取键函数都行（internet-asset 用函数拼复合键）
  rowKey?: string | ((row: any) => any)
  highlightCurrentRow?: boolean
}>()

const emit = defineEmits<{
  (e: 'row-click', row: any): void
  (e: 'row-dblclick', row: any, column: any, event: MouseEvent): void
  // 列宽拖拽（el-table 原生：border + 表头右缘拖动）；宽度持久化由页面接 useTablePrefs 处理
  (e: 'header-dragend', newWidth: number, oldWidth: number, column: any, event: MouseEvent): void
}>()

const tableRef = ref()

/** 透传内层 el-table 的 setCurrentRow（页面在数据重建后恢复当前行高亮用）；需要别的内层 API 在这里继续转发 */
const setCurrentRow = (row: any) => tableRef.value?.setCurrentRow(row)

// 未声明的属性 / 事件（span-method、row-class-name、class 等）由 Vue 原样落到根元素 el-table 上
defineExpose({ setCurrentRow })
</script>

<template>
  <el-table
    ref="tableRef"
    v-loading="loading"
    :data="data"
    :stripe="stripe !== false"
    :border="border !== false"
    :height="height || '100%'"
    :size="size"
    :row-key="rowKey"
    :highlight-current-row="highlightCurrentRow"
    style="width: 100%"
    @row-click="(row: any) => emit('row-click', row)"
    @row-dblclick="(row: any, column: any, event: MouseEvent) => emit('row-dblclick', row, column, event)"
    @header-dragend="(newWidth: number, oldWidth: number, column: any, event: MouseEvent) => emit('header-dragend', newWidth, oldWidth, column, event)"
  >
    <slot />
  </el-table>
</template>
