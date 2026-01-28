// 简化的表格组件类型定义
export interface TableColumn {
  prop: string
  label: string
  width?: string | number
  minWidth?: string | number
  sortable?: boolean
  align?: 'left' | 'center' | 'right'
  showOverflowTooltip?: boolean
  formatter?: (row: any, column: TableColumn, cellValue: any, index: number) => any
  renderCell?: (scope: { row: any, column: TableColumn, $index: number }) => any
  type?: 'selection' | 'index'
}

export interface TablePagination {
  currentPage?: number
  pageSize?: number
  total?: number
  pageSizes?: number[]
  layout?: string
}

export interface TableSelection {
  selectedRows?: any[]
  onSelectionChange?: (selection: any[]) => void
}