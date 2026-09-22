<script setup lang="ts">
defineProps<{
  data: any[]
  loading?: boolean
  height?: string
  stripe?: boolean
  border?: boolean
  size?: 'large' | 'default' | 'small'
  rowKey?: string
  highlightCurrentRow?: boolean
}>()

defineEmits<{
  (e: 'row-click', row: any): void
  // 列宽拖拽（el-table 原生：border + 表头右缘拖动）；宽度持久化由页面接 useTablePrefs 处理
  (e: 'header-dragend', newWidth: number, oldWidth: number, column: any, event: MouseEvent): void
}>()
</script>

<template>
  <el-table
    v-loading="loading"
    :data="data"
    :stripe="stripe !== false"
    :border="border !== false"
    :height="height || '100%'"
    :size="size"
    :row-key="rowKey"
    :highlight-current-row="highlightCurrentRow"
    style="width: 100%"
    @row-click="(row: any) => $emit('row-click', row)"
    @header-dragend="(newWidth: number, oldWidth: number, column: any, event: MouseEvent) => $emit('header-dragend', newWidth, oldWidth, column, event)"
  >
    <slot />
  </el-table>
</template>
