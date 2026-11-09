import type { InjectionKey } from 'vue'

/**
 * DataTable → DataColumn 的上下文：列从这里拿「偏好感知的列宽解析」。
 *
 * 宽度语义（在 DataColumn 内部落地）：
 * - 锚点列（anchor 或 fixed 列）：`width` 是**固定宽**，所拖即所得；
 * - 内容列（默认）：`width` / `min-width` 是**下限**，参与容器富余空间的比例分配，
 *   保证列总宽至少 100%、超出即横向滚动。
 *
 * 没挂 `table-key` 的表格 provide 一个纯回退实现：直接返回页面给的默认值，无持久化。
 */
export const dataTableKey: InjectionKey<{
  widthFor: (columnKey: string, fallback?: number | string) => number | string | undefined
}> = Symbol('data-table')
