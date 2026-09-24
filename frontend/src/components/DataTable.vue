<script lang="ts">
import { cloneVNode, defineComponent, Fragment, h, provide, ref, useSlots, withDirectives } from 'vue'
import { ElLoadingDirective, ElTable } from 'element-plus'
import { useTablePrefs } from '@/composables/useTablePrefs'
import { dataTableKey } from './tableContext'
import ColumnSettings from './ColumnSettings.vue'

import type { PropType, VNode } from 'vue'
import type { TableKey } from '@/types'

/**
 * 表格容器（render 版）：在 el-table 之上内建两件事——
 *
 * ① 列宽偏好：读（DataColumn 经 context 取）与写（header-dragend 拖拽持久化）都在这里；
 * ② 列设置（方案 C）：默认插槽的列 vnode 按「列布局偏好」重排 + 隐藏过滤后渲染，
 *    挂 table-key 的表格右上角悬浮「列设置」按钮（顺序/显隐弹窗）。
 *
 * **为什么是 render 函数而不是模板**：列的顺序只能在 slot vnode 层面重排，
 * 模板的 <slot /> 无法调整 vnode 顺序；v-if/v-else 的列组是 Fragment，需逐层摊平。
 *
 * 契约不变：props/emit/expose 与模板版一致；未声明的属性 / 事件
 * （span-method、row-class-name、tree-props、default-expand-all…）由 attrs 原样落到 el-table。
 */
export default defineComponent({
  name: 'DataTable',
  props: {
    data: { type: Array as PropType<any[]>, required: true },
    loading: { type: Boolean, default: false },
    height: { type: String, default: '' },
    stripe: { type: Boolean, default: true },
    border: { type: Boolean, default: true },
    size: { type: String as PropType<'large' | 'default' | 'small'>, default: undefined },
    rowKey: { type: [String, Function] as PropType<string | ((row: any) => any)>, default: undefined },
    highlightCurrentRow: { type: Boolean, default: false },
    /**
     * 表格 key（取自 constants/tableKeys.ts 的 TABLE_KEYS）。
     * 挂上即获得：列宽偏好持久化 + 列设置（顺序/显隐）；不挂则列宽用页面默认值、无列设置按钮。
     */
    tableKey: { type: String as PropType<TableKey>, default: undefined },
  },
  emits: {
    'row-click': (_row: any) => true,
    'row-dblclick': (_row: any, _column: any, _event: MouseEvent) => true,
    // 列宽拖拽仍向外转发（页面想做别的事可监听）；持久化已内建
    'header-dragend': (_newWidth: number, _oldWidth: number, _column: any, _event: MouseEvent) => true,
  },
  setup(props, { attrs, slots, emit, expose }) {
    // 单实例管偏好：列宽读取与写入、列布局（顺序/显隐）都在这里
    const prefs = props.tableKey ? useTablePrefs(props.tableKey) : null

    provide(dataTableKey, {
      widthFor: (columnKey: string, fallback?: number | string) =>
        prefs ? prefs.widthFor(columnKey, fallback) : fallback,
    })

    const tableRef = ref()
    /** 透传内层 el-table 的 setCurrentRow（页面在数据重建后恢复当前行高亮用）；需要别的内层 API 在这里继续转发 */
    const setCurrentRow = (row: any) => tableRef.value?.setCurrentRow(row)
    expose({ setCurrentRow })

    /** 默认插槽 vnode 摊平（v-if/v-else 列组是 Fragment，逐层展开成单列） */
    const flatten = (nodes: VNode[]): VNode[] =>
      nodes.flatMap((n) =>
        n && n.type === Fragment && Array.isArray(n.children) ? flatten(n.children as VNode[]) : [n],
      )

    /** 列标识：column-key > prop；两者都没有的列不参与排序/隐藏，按槽序固定在尾部 */
    const keyOf = (vnode: VNode) => {
      const p = (vnode.props ?? {}) as Record<string, any>
      return String(p.columnKey || p['column-key'] || p.prop || '')
    }

    const labelOf = (vnode: VNode) => {
      const p = (vnode.props ?? {}) as Record<string, any>
      const key = keyOf(vnode)
      return String(p.label ?? key)
    }

    return () => {
      // 每次渲染现算（不 computed）：slot 执行时读到的响应式（v-if 条件等）只在渲染期建立依赖，
      // computed 缓存有过不更新的坑；列数量小，重算零成本
      const columns = flatten(slots.default?.() ?? []).filter((v) => v && typeof v.type === 'object')

      let ordered = columns
      if (prefs) {
        const order = prefs.columnOrder.value
        const hidden = prefs.hiddenKeys.value
        const rank = (key: string) => {
          const idx = order.indexOf(key)
          return idx < 0 ? Number.MAX_SAFE_INTEGER : idx
        }
        ordered = columns
          .filter((v) => !hidden.has(keyOf(v)))
          .map((v, i) => ({ v, i }))
          .sort((a, b) => rank(keyOf(a.v)) - rank(keyOf(b.v)) || a.i - b.i)
          .map(({ v }) => v)
      }
      // 补稳定 key：排序/过滤后的数组按 index diff 会串列
      const rendered = ordered.map((v, i) => cloneVNode(v, { key: keyOf(v) || `col-${i}` }))

      const table = h(
        ElTable,
        {
          ref: tableRef,
          data: props.data,
          height: props.height || '100%',
          stripe: props.stripe,
          border: props.border,
          size: props.size,
          rowKey: props.rowKey,
          highlightCurrentRow: props.highlightCurrentRow,
          ...attrs,
          onRowClick: (row: any) => emit('row-click', row),
          onRowDblclick: (row: any, column: any, event: MouseEvent) =>
            emit('row-dblclick', row, column, event),
          onHeaderDragend: (newWidth: number, oldWidth: number, column: any, event: MouseEvent) => {
            prefs?.onHeaderDragend(newWidth, oldWidth, column)
            emit('header-dragend', newWidth, oldWidth, column, event)
          },
        },
        { default: () => rendered },
      )
      const withLoading = props.loading ? withDirectives(table, [[ElLoadingDirective, props.loading]]) : table

      if (!props.tableKey) return withLoading
      return h('div', { class: 'dt-root' }, [
        withLoading,
        h(ColumnSettings, {
          tableKey: props.tableKey,
          columns: columns.filter((v) => keyOf(v)).map((v) => ({ key: keyOf(v), label: labelOf(v) })),
        }),
      ])
    }
  },
})
</script>

<style scoped>
.dt-root { position: relative; height: 100%; }
</style>
