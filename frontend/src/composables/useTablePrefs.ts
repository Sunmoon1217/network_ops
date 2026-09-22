import { ref, computed } from 'vue'
import { getPreferences, savePreference } from '@/api/preferences'
import { getToken } from '@/utils/token'

import type { DraggableColumn, TableColumnWidths, UserPreferences } from '@/types'

/**
 * 用户前端偏好的模块级缓存：整个会话只在首次用到时拉一次，
 * 同一用户开多个页面共享同一份；登录 / 登出时由 auth store 调 resetUserPreferences() 清空。
 */
const preferences = ref<UserPreferences>({})
let loadPromise: Promise<void> | null = null

const ensureLoaded = () => {
  // 未登录不请求：401 会被 axios 拦截器当成登录失效跳 /login
  if (!getToken()) return Promise.resolve()
  if (!loadPromise) {
    loadPromise = getPreferences()
      .then((data) => {
        preferences.value = data ?? {}
      })
      .catch(() => {
        // 拉取失败不打断页面（偏好只是锦上添花），清掉 promise 允许下次重试
        loadPromise = null
      })
  }
  return loadPromise
}

/** 登录 / 登出后清空缓存，避免拿到上一个账号的偏好 */
export const resetUserPreferences = () => {
  preferences.value = {}
  loadPromise = null
}

/** 每个偏好键一个防抖计时器（模块级：连续拖多列只回写最后一次） */
const saveTimers: Record<string, number> = {}

const flushPreference = (prefKey: string) => {
  if (!getToken()) return // 会话中途登出就只留在本地
  savePreference({ key: prefKey, value: preferences.value[prefKey] }).catch(() => {
    // 回写失败静默：偏好不是关键数据，不打扰用户
  })
}

export const useTablePrefs = (tableKey: string) => {
  const prefKey = `table:${tableKey}:column-widths`
  ensureLoaded()

  const widths = computed(() => (preferences.value[prefKey] ?? {}) as TableColumnWidths)

  /** 取某列保存的宽度；没有保存过就回退到页面默认宽度（或 undefined，走 min-width） */
  const widthFor = (columnKey: string, fallback?: number | string) => widths.value[columnKey] ?? fallback

  /** 挂到 el-table 的 @header-dragend：本地立即生效，防抖回写后端 */
  const onHeaderDragend = (newWidth: number, _oldWidth: number, column: DraggableColumn) => {
    // 列标识优先级：column-key > prop > Element 内部 id（操作列这类无 prop 的列要显式给 column-key）
    const columnKey = column.columnKey || column.property || column.id
    if (!columnKey) return
    preferences.value = {
      ...preferences.value,
      [prefKey]: { ...widths.value, [columnKey]: newWidth },
    }
    window.clearTimeout(saveTimers[prefKey])
    saveTimers[prefKey] = window.setTimeout(() => flushPreference(prefKey), 500)
  }

  return { prefKey, widths, widthFor, onHeaderDragend, ensureLoaded }
}
