<script setup lang="ts">
import { computed, inject, useSlots } from 'vue'
import { dataTableKey } from './tableContext'

/**
 * 表格列：el-table-column 的薄封装，负责两件事——
 * ① 列宽接偏好（列 key = column-key > prop；值经 DataTable 下发的 widthFor 解析）；
 * ② 按列角色选宽度档位：锚点列（anchor 或 fixed）用固定 `width`，
 *    内容列用 `min-width` 参与填满（列总宽 ≥ 容器，超出滚动）。
 *
 * 单元格内容照旧用默认插槽写（el-tag / 按钮 / 任意组件），不给插槽时
 * 走 el-table-column 原生的 `row[prop]` 文本渲染；未声明的属性照旧落到内层列上。
 */
const props = defineProps<{
  prop?: string
  label?: string
  /** 锚点列＝固定宽；内容列＝初始下限（参与填充） */
  width?: number | string
  /** 显式下限（原 min-width 语义），内容列下限时优先于 width */
  minWidth?: number | string
  /** 强制锚点列；不传时 fixed 列（操作列等）默认就是锚点 */
  anchor?: boolean
  columnKey?: string
  fixed?: boolean | 'left' | 'right'
  sortable?: boolean | string
  align?: 'left' | 'right' | 'center'
  showOverflowTooltip?: boolean
}>()

const slots = useSlots()
const ctx = inject(dataTableKey, null)

/** 偏好字典里的列标识，与 useTablePrefs 的取键优先级一致：column-key > prop */
const columnKeyOf = computed(() => props.columnKey || props.prop || '')

const isAnchor = computed(() => props.anchor ?? !!props.fixed)

/** 该档位的基准值：偏好存过就用偏好，否则回退页面默认 */
const base = computed(() => {
  const fallback = props.minWidth ?? props.width
  if (fallback === undefined) return undefined
  return columnKeyOf.value && ctx ? ctx.widthFor(columnKeyOf.value, fallback) : fallback
})

/** 锚点列固定宽；无偏好上下文时锚点列也退回原值 */
const elWidth = computed(() => (isAnchor.value ? base.value : undefined))
/** 内容列一律走 min-width（显式 minWidth 优先，锚点列仅保留页面显式声明） */
const elMinWidth = computed(() => {
  if (!isAnchor.value) return base.value
  return props.minWidth
})
</script>

<template>
  <el-table-column
    :prop="prop"
    :label="label"
    :width="elWidth"
    :min-width="elMinWidth"
    :column-key="columnKey"
    :fixed="fixed"
    :sortable="sortable"
    :align="align"
    :show-overflow-tooltip="showOverflowTooltip"
  >
    <template v-if="slots.default" #default="scope">
      <slot v-bind="scope" />
    </template>
  </el-table-column>
</template>
