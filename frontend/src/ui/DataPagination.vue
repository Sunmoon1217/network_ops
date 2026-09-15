<script setup lang="ts">
withDefaults(
  defineProps<{
    page: number
    pageSize: number
    total: number
    pageSizes?: number[]
    layout?: string
  }>(),
  {
    pageSizes: () => [20, 50, 100, 200],
    layout: 'total, sizes, prev, pager, next, jumper',
  }
)

const emit = defineEmits<{
  (e: 'update:page', v: number): void
  (e: 'update:pageSize', v: number): void
  (e: 'change'): void
}>()

function handlePage(p: number) {
  emit('update:page', p)
  emit('change')
}

function handleSize(s: number) {
  emit('update:pageSize', s)
  emit('update:page', 1)
  emit('change')
}
</script>

<template>
  <div class="data-pagination">
    <el-pagination
      :current-page="page"
      :page-size="pageSize"
      :total="total"
      :page-sizes="pageSizes"
      :layout="layout"
      background
      @current-change="handlePage"
      @size-change="handleSize"
    />
  </div>
</template>

<style scoped>
.data-pagination {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding: 10px 4px 0;
  flex-shrink: 0;
}
</style>
