export interface ChartData {
  name: string
  time?: number[]
  value: number[]
  color?: string
}

export interface ChartDataGroup {
  title: string
  data: ChartData[]
}

export interface LineChartsProps {
  data: Array<ChartData[] | ChartDataGroup>
  xAxisData: Array<string>
  yAxisName?: string
  title?: string
  theme?: string
  height?: string
  width?: string
  loading?: boolean
}

export interface LinkData {
  name: string
  value: number[]
}

// gauge 单个数据项：可由调用方携带 title/detail 覆盖项，用于控制文字位置等
export interface GaugeDataItem {
  name: string
  value: number
  title?: {
    show?: boolean
    offsetCenter?: [string, string]
    fontSize?: string
    color?: string
  }
  detail?: {
    show?: boolean
    offsetCenter?: [string, string]
    fontSize?: string
    color?: string
    formatter?: string
  }
}

export interface GaugeChartsProps {
  data?: GaugeDataItem[]
  title?: string
  theme?: string
  height?: string
  width?: string
  loading?: boolean
}

export interface BarChartsProps {
  data: Array<{ name: string; value: number }>
  yAxisName?: string
  title?: string
  theme?: string
  height?: string
  width?: string
  loading?: boolean
}
