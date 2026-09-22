/** 用户前端偏好（表格列宽等界面配置）：偏好键 → 任意 JSON 值 */
export type UserPreferences = Record<string, unknown>

/** 列宽映射：列 key（el-table-column 的 column-key / prop）→ 像素宽度 */
export type TableColumnWidths = Record<string, number>

/** PUT /api/me/preferences/ 的单条载荷（后端按 key upsert，不做全量替换） */
export interface PreferencePayload {
    key: string
    value: unknown
}

/** header-dragend 给出的列对象（Element Plus 的 TableColumnCtx，只取用得到的三个标识位） */
export type DraggableColumn = { columnKey?: string; property?: string; id?: string }
