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

export interface GaugeChartsProps {
  data?: Array<{ name: string; value: number }>
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
