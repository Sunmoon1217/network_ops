<script setup lang="ts">
import { provide, ref } from 'vue'
import { useTablePrefs } from '@/composables/useTablePrefs'
import { dataTableKey } from './tableContext'

import type { TableKey } from '@/types'

const props = defineProps<{
  data: any[]
  loading?: boolean
  height?: string
  stripe?: boolean
  border?: boolean
  size?: 'large' | 'default' | 'small'
  rowKey?: string | ((row: any) => any)
  highlightCurrentRow?: boolean
  /**
   * 表格 key（取自 constants/tableKeys.ts 的 TABLE_KEYS）。
   * 挂上即获得：列宽偏好持久化（内部接 header-dragend）+ 下发给 DataColumn 的偏好感知列宽；
   * 不挂则列宽用页面默认值、不持久化。
   */
  tableKey?: TableKey
}>()

const emit = defineEmits<{
  (e: 'row-click', row: any): void
  (e: 'row-dblclick', row: any, column: any, event: MouseEvent): void
  // 列宽拖拽仍向外转发（页面想做别的事可监听）；持久化已内建，不再要求页面自己接
  (e: 'header-dragend', newWidth: number, oldWidth: number, column: any, event: MouseEvent): void
}>()

// 单实例管偏好：读（DataColumn 经 context 取）与写（下方拖拽处理）都在这里
const prefs = props.tableKey ? useTablePrefs(props.tableKey) : null

provide(dataTableKey, {
  widthFor: (columnKey: string, fallback?: number | string) =>
    prefs ? prefs.widthFor(columnKey, fallback) : fallback,
})

const onHeaderDragend = (newWidth: number, oldWidth: number, column: any, event: MouseEvent) => {
  prefs?.onHeaderDragend(newWidth, oldWidth, column)
  emit('header-dragend', newWidth, oldWidth, column, event)
}

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
    @header-dragend="onHeaderDragend"
  >
    <slot />
  </el-table>
</template>
