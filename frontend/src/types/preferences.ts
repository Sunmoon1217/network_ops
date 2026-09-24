import { TABLE_KEYS } from '@/constants/tableKeys'

/** 已注册的表格 key（useTablePrefs 的唯一合法入参）——由注册表派生，往 TABLE_KEYS 加键即进联合类型 */
export type TableKey = (typeof TABLE_KEYS)[keyof typeof TABLE_KEYS]

/** 用户前端偏好（表格列宽等界面配置）：偏好键 → 任意 JSON 值 */
export type UserPreferences = Record<string, unknown>

/** 列宽映射：列 key（el-table-column 的 column-key / prop）→ 像素宽度 */
export type TableColumnWidths = Record<string, number>

/**
 * 列布局偏好（列设置弹窗的产物）：
 * - `order`：列 key 顺序（未登记的列按默认槽序排在尾部）；
 * - `hidden`：被隐藏的列 key。
 * 与列宽分开存偏好键（列宽是裸 key→宽度映射，塞结构字段会与名为 order/hidden 的列撞 key）。
 */
export interface TableColumnLayout {
    order?: string[]
    hidden?: string[]
}

/** 列设置弹窗的列元数据（DataTable 从默认插槽 vnode 提取后喂给弹窗） */
export interface ColumnMeta {
    key: string
    label: string
}

/** PUT /api/me/preferences/ 的单条载荷（后端按 key upsert，不做全量替换） */
export interface PreferencePayload {
    key: string
    value: unknown
}

/** header-dragend 给出的列对象（Element Plus 的 TableColumnCtx，只取用得到的三个标识位） */
export type DraggableColumn = { columnKey?: string; property?: string; id?: string }
