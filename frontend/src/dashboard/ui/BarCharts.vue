<template>
  <div ref="chartRef" class="line-charts"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import type { BarChartsProps } from '@/types'
import echarts from './utils/echarts'

// 默认值
const props = withDefaults(defineProps<BarChartsProps>(), {
  data: () => [],
  yAxisName: '数值',
  title: '折线图',
  theme: 'light',
  height: '400px',
  width: '100%',
  loading: false,
})

const chartRef = ref<HTMLDivElement | null>(null)
let myChart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null
const barPalette = ['#34c8ff', '#6ff4ff', '#3dde9f', '#ffd35e', '#9f92ff', '#ff6c84']
const formatAxisLabel = (label: string) => {
  if (label.length <= 4) return label
  if (label.length <= 6) return `${label.slice(0, 3)}\n${label.slice(3)}`
  return `${label.slice(0, 4)}\n${label.slice(4, 8)}`
}
const formatYAxisLabel = (value: number) => {
  if (value === 0 || value === 100) return `${value}%`
  return `${Math.round(value)}`
}
const handleResize = () => {
  if (!myChart || !chartRef.value) return
  myChart.resize({
    width: chartRef.value.clientWidth,
    height: chartRef.value.clientHeight,
  })
}

// 初始化图表
const initChart = () => {
  if (!chartRef.value) return
  myChart = echarts.init(chartRef.value)
  updateChart()
}
// 更新图表数据
const updateChart = () => {
  if (!myChart) return
  const option = {
    xAxis: {
      type: 'category',
      data: props.data.map((d) => d.name),
      axisLabel: {
        color: '#9dbcd7',
        rotate: 0,
        margin: 10,
        fontSize: 10,
        interval: 0,
        lineHeight: 13,
        formatter: (value: string) => formatAxisLabel(value),
      },
      axisTick: {
        show: false,
      },
      axisLine: {
        lineStyle: {
          color: 'rgba(111, 244, 255, 0.25)',
        },
      },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      interval: 25,
      axisLabel: {
        fontSize: 9,
        color: '#9dbcd7',
        margin: 8,
        formatter: (value: number) => formatYAxisLabel(value),
      },
      axisTick: {
        show: false,
      },
      axisLine: {
        show: false,
      },
      splitLine: {
        lineStyle: {
          color: 'rgba(111, 244, 255, 0.12)',
          type: 'dashed',
        },
      },
    },
    grid: {
      left: 4,
      right: 24,
      top: 12,
      bottom: 4,
      containLabel: false,
    },
    series: {
      type: 'bar',
      smooth: true,
      data: props.data,
      symbol: 'none',
      barWidth: '50%',
      itemStyle: {
        borderRadius: [8, 8, 0, 0],
        color: (params: { dataIndex: number }) => {
          const color = barPalette[params.dataIndex % barPalette.length] ?? '#34c8ff'
          return new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color },
            { offset: 1, color: color + '99' },
          ])
        },
      },
      emphasis: {
        itemStyle: {
          shadowBlur: 8,
          shadowColor: 'rgba(52, 200, 255, 0.35)',
        },
      },
    },
  }
  myChart.setOption(option)
}

onMounted(() => {
  initChart()
  window.addEventListener('resize', handleResize)
  if (chartRef.value) {
    resizeObserver = new ResizeObserver(() => {
      handleResize()
    })
    resizeObserver.observe(chartRef.value)
  }
  handleResize()
})

watch(
  () => props.data,
  () => {
    updateChart()
    handleResize()
  },
  { deep: true },
)

// 清理监听
onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  resizeObserver?.disconnect()
  resizeObserver = null
  myChart?.dispose()
  myChart = null
})
</script>

<style scoped>
.line-charts {
  width: 100%;
  height: 100%;
  margin: 0 auto;
  box-sizing: border-box;
}
</style>
