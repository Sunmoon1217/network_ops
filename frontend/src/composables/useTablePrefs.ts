import { ref, computed } from 'vue'
import { getPreferences, savePreference } from '@/api/preferences'
import { getToken } from '@/utils/token'
import { TABLE_KEY_RENAMES } from '@/constants/tableKeys'

import type { DraggableColumn, TableColumnLayout, TableColumnWidths, TableKey, UserPreferences } from '@/types'

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

/** tableKey → 偏好键（`table:<key>:column-widths`） */
const prefKeyOf = (tableKey: string) => `table:${tableKey}:column-widths`

/** tableKey → 列布局偏好键（`table:<key>:column-layout`，存 {order, hidden}） */
const layoutKeyOf = (tableKey: string) => `table:${tableKey}:column-layout`

/**
 * @param tableKey 只接受注册表里的 key（`TABLE_KEYS.xxx`），拼错/未注册编译期即报错——
 *   后端不解析 key，撞名或写错的后果只能由前端在这里挡住
 */
export const useTablePrefs = (tableKey: TableKey) => {
  const prefKey = prefKeyOf(tableKey)
  ensureLoaded()

  // key 改名回退：新键还没数据时读旧键（TABLE_KEY_RENAMES 登记过 旧→新 才生效）；
  // 一旦拖动任意一列，写回的就是新键 = 整份宽度完成迁移
  const legacyKey = Object.keys(TABLE_KEY_RENAMES).find((old) => TABLE_KEY_RENAMES[old] === tableKey)

  const widths = computed(() => {
    const current = preferences.value[prefKey]
    if (current) return current as TableColumnWidths
    if (legacyKey) return (preferences.value[prefKeyOf(legacyKey)] ?? {}) as TableColumnWidths
    return {}
  })

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

  // ── 列布局（列设置弹窗）：顺序与显隐，独立偏好键存取 ──────────────────────
  const layoutPrefKey = layoutKeyOf(tableKey)

  const layout = computed(() => {
    const current = preferences.value[layoutPrefKey]
    if (current) return current as TableColumnLayout
    if (legacyKey) return (preferences.value[layoutKeyOf(legacyKey)] ?? {}) as TableColumnLayout
    return {}
  })

  /** 列 key 顺序；空数组 = 默认槽序 */
  const columnOrder = computed(() => layout.value.order ?? [])
  /** 被隐藏的列 key 集合 */
  const hiddenKeys = computed(() => new Set(layout.value.hidden ?? []))

  const saveLayout = (patch: Partial<TableColumnLayout>) => {
    preferences.value = {
      ...preferences.value,
      [layoutPrefKey]: { ...layout.value, ...patch },
    }
    window.clearTimeout(saveTimers[layoutPrefKey])
    saveTimers[layoutPrefKey] = window.setTimeout(() => flushPreference(layoutPrefKey), 500)
  }

  /** 上/下移一列（order 里没有的 key 先按当前有效序展开再移动） */
  const moveColumn = (key: string, delta: -1 | 1) => {
    const effective = [...new Set([...columnOrder.value, key])]
    const from = effective.indexOf(key)
    const to = from + delta
    if (from < 0 || to < 0 || to >= effective.length) return
    ;[effective[from], effective[to]] = [effective[to], effective[from]]
    saveLayout({ order: effective })
  }

  /** 切换列显隐 */
  const toggleColumn = (key: string) => {
    const hidden = new Set(layout.value.hidden ?? [])
    if (hidden.has(key)) hidden.delete(key)
    else hidden.add(key)
    saveLayout({ hidden: [...hidden] })
  }

  /** 恢复默认布局（删偏好条目，value=null 即删） */
  const resetColumnLayout = () => {
    const next = { ...preferences.value }
    delete next[layoutPrefKey]
    preferences.value = next
    if (getToken()) savePreference({ key: layoutPrefKey, value: null }).catch(() => {})
  }

  return {
    prefKey,
    widths,
    widthFor,
    onHeaderDragend,
    ensureLoaded,
    columnOrder,
    hiddenKeys,
    moveColumn,
    toggleColumn,
    resetColumnLayout,
  }
}
