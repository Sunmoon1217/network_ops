import type { Column } from 'element-plus/es/components/table-v2/src/types'

export interface Options {
  label: string
  value: string
}

export interface SearchFieldConfig {
  prop: string
  label: string
  type?: 'input' | 'select' | 'date'
  options?: Options[]
  placeholder?: string
  instantSearch?: boolean
  debounceMs?: number
}

export interface CursorPaginationState {
  cursor: string | null
  nextCursor: string | null
  prevCursor: string | null
  limit: number
  hasNext: boolean
  hasprev: boolean
}

export interface TableViewConfig {
  title: string
  apiUrl: string
  columns: Column<any>[]
  searchFields: SearchFieldConfig[]
  defaultLimit?: number
  actions?: {
    label: string
    onClick: (row: any) => void
  }[]
}
