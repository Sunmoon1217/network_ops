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
  >
    <slot />
  </el-table>
</template>
