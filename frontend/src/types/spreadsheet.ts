/** 通用表格（xlsx 编辑与历史，/api/sheets/，后端 sheets 应用） */

/** 单元格值：JSON 标量（空单元格为 null） */
export type SheetCellValue = string | number | boolean | null

/** 一张表的矩形网格；rows[0] 是表头行（列名），行/列都是定长数组 */
export interface SheetData {
  name: string
  rows: SheetCellValue[][]
}

/** 前后端唯一交换格式：整个工作簿 */
export interface SpreadsheetData {
  sheets: SheetData[]
}

/** 工作簿列表条目（不含数据） */
export interface SpreadsheetSummary {
  id: number
  name: string
  sheet_names: string[]
  latest_revision: number
  created_by: string | null
  updated_by: string | null
  created_at: string
  updated_at: string
}

/** 工作簿详情（含当前数据） */
export interface SpreadsheetDetail extends SpreadsheetSummary {
  data: SpreadsheetData
}

/** 变更计数（历史列表直接展示的摘要） */
export interface SheetChangeSummary {
  cells_changed: number
  rows_added: number
  rows_removed: number
  sheets_added: number
  sheets_removed: number
  truncated: boolean
}

/** 单元格级变更（row/col 是网格索引，row 0 即表头行） */
export interface SheetCellChange {
  sheet: string
  row: number
  col: number
  old: SheetCellValue
  new: SheetCellValue
}

/** 历史版本（列表条目） */
export interface SpreadsheetRevision {
  id: number
  revision: number
  note: string
  summary: SheetChangeSummary
  created_by: string | null
  created_at: string
}

/** 历史版本详情（全量快照 + 相对上一版本的变更明细） */
export interface SpreadsheetRevisionDetail extends SpreadsheetRevision {
  changes: SheetCellChange[]
  data: SpreadsheetData
}

/** 保存 / 恢复接口的返回（created=false 表示无改动、没有落新版本） */
export interface SpreadsheetSaveResult {
  created: boolean
  revision: number
  changes: SheetCellChange[]
  summary: SheetChangeSummary
}
