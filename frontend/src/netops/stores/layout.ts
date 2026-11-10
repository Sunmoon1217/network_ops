import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useLayoutStore = defineStore('layout', () => {
  const viewtitle = ref('默认标题')

  const collapsed = ref(localStorage.getItem('sidebarCollapsed') === 'true')

  const SIDEBAR_WIDTH = 180
  const SIDEBAR_COLLAPSED_WIDTH = 56

  const sidebarWidth = computed(() =>
    collapsed.value ? SIDEBAR_COLLAPSED_WIDTH : SIDEBAR_WIDTH,
  )

  const toggleCollapsed = () => {
    collapsed.value = !collapsed.value
    localStorage.setItem('sidebarCollapsed', String(collapsed.value))
  }

  return { viewtitle, collapsed, sidebarWidth, SIDEBAR_WIDTH, SIDEBAR_COLLAPSED_WIDTH, toggleCollapsed }
})
