import { markRaw } from 'vue'
import { use } from 'echarts/core'
import { PieChart, BarChart, GaugeChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, LegendComponent, GridComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([PieChart, BarChart, GaugeChart, TitleComponent, TooltipComponent, LegendComponent, GridComponent, CanvasRenderer])

export const COLORS = ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272', '#fc8452', '#9a60b4', '#ea7ccc', '#48b8d0']

export function lookup(map: Record<string, string>, key: string, fallback = '未知'): string {
  return map[key] ?? fallback
}

export function mapItems(arr: { name: string; value: number }[]) {
  return arr.map(i => ({ name: i.name || '未知', value: i.value }))
}

export function pieOpt(title: string, items: { name: string; value: number }[], radius = ['40%', '70%']) {
  return markRaw({
    title: { text: title, left: 'center', textStyle: { fontSize: 13, fontWeight: 600 } },
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    color: COLORS,
    series: [{
      type: 'pie', radius, center: ['50%', '55%'],
      label: { fontSize: 11 },
      data: items.filter(i => i.value > 0),
    }],
  })
}

export function barOpt(title: string, categories: string[], values: number[], horizontal = false) {
  const axis = horizontal
    ? { xAxis: { type: 'value' }, yAxis: { type: 'category', data: categories, axisLabel: { fontSize: 11 } } }
    : { xAxis: { type: 'category', data: categories, axisLabel: { rotate: 30, fontSize: 10 } }, yAxis: { type: 'value' } }
  return markRaw({
    title: { text: title, left: 'center', textStyle: { fontSize: 13, fontWeight: 600 } },
    tooltip: { trigger: 'axis' },
    color: COLORS,
    grid: { top: 40, bottom: 50, left: horizontal ? 80 : 40, right: 20 },
    ...axis,
    series: [{ type: 'bar', data: values, barMaxWidth: 32, itemStyle: { borderRadius: [4, 4, 0, 0] } }],
  })
}

export function gaugeOpt(title: string, value: number, max: number) {
  return markRaw({
    title: { text: title, left: 'center', textStyle: { fontSize: 13, fontWeight: 600 } },
    series: [{
      type: 'gauge', center: ['50%', '60%'], radius: '80%',
      progress: { show: true, width: 14 },
      axisLine: { lineStyle: { width: 14 } },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: { show: false },
      pointer: { show: false },
      detail: { valueAnimation: true, fontSize: 22, fontWeight: 700, offsetCenter: [0, '10%'], formatter: `{value}/${max}` },
      data: [{ value }],
      max,
    }],
  })
}

export function lineOpt(title: string, xData: string[], yData: number[], unit = '') {
  return markRaw({
    title: { text: title, left: 'center', textStyle: { fontSize: 13, fontWeight: 600 } },
    tooltip: { trigger: 'axis', formatter: (params: any) => `${params[0].axisValue}: ${params[0].value}${unit}` },
    color: COLORS,
    grid: { top: 40, bottom: 30, left: 50, right: 20 },
    xAxis: { type: 'category', data: xData, axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value', axisLabel: { formatter: `{value}${unit}` } },
    series: [{
      type: 'line',
      data: yData,
      smooth: true,
      areaStyle: { opacity: 0.15 },
      itemStyle: { borderRadius: [4, 4, 0, 0] },
    }],
  })
}
