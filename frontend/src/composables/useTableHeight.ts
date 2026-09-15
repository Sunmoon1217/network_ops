import { ref, onMounted, onUnmounted, nextTick } from 'vue'

export const useTableHeight = () => {
  const tableRef = ref<HTMLElement | null>(null)
  const tableHeight = ref(600)
  const tableWidth = ref(1200)

  const updateSize = () => {
    if (tableRef.value) {
      tableHeight.value = tableRef.value.clientHeight
      tableWidth.value = tableRef.value.clientWidth
    }
  }

  onMounted(() => {
    nextTick(updateSize)
    window.addEventListener('resize', updateSize)
  })

  onUnmounted(() => {
    window.removeEventListener('resize', updateSize)
  })

  return { tableRef, tableHeight, tableWidth }
}
