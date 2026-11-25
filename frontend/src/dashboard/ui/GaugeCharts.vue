<template>
  <div ref="chartRef" class="gaugecharts"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import echarts from '@dashboard/utils/echarts'
import type { GaugeChartsProps } from '@dashboard/types'

// 默认值
const props = withDefaults(defineProps<GaugeChartsProps>(), {
  data: () => [],
  title: '',
  theme: 'light',
  height: '400px',
  width: '100%',
  loading: false,
})
const chartRef = ref<HTMLDivElement | null>(null)
let myChart: echarts.ECharts | null = null
let carouselInterval: number | null = null
const handleResize = () => myChart?.resize()

// 多指标布局：每个指标占一行（数值在左、名称在右，同一 y），指标之间上下错开。
// 注意 offsetCenter 百分比基准是仪表盘半径（卡片内约 50px）。
// 单指标保持原样（弧线下方居中，数值上、名称下）。
const transformData = (data: Array<{ name: string; value: number }>) => {
  const count = Math.max(data.length, 1)
  const spanY = 26 // 首尾指标行的纵向偏移（半径百分比）
  const xGap = 24 // 单行内数值与名称的横向偏移
  return data.map((item, i) => {
    if (count === 1) {
      return {
        ...item,
        title: { show: true, offsetCenter: ['0', '46%'], fontSize: '0.7rem', color: '#b6d7ef' },
        detail: {
          show: true,
          offsetCenter: ['0', '16%'],
          width: 10,
          fontSize: '0.78rem',
          color: '#ecf7ff',
          formatter: '{value}%',
        },
      }
    }
    // n>1：每行一个指标，行中心从 -spanY 均匀分布到 +spanY
    const yc = ((i / (count - 1)) * 2 - 1) * spanY
    return {
      ...item,
      title: {
        show: true,
        offsetCenter: [`${xGap}%`, `${yc.toFixed(1)}%`],
        fontSize: '0.7rem',
        color: '#b6d7ef',
      },
      detail: {
        show: true,
        offsetCenter: [`${-xGap}%`, `${yc.toFixed(1)}%`],
        width: 10,
        fontSize: '0.78rem',
        color: '#ecf7ff',
        formatter: '{value}%',
      },
    }
  })
}

// 初始化图表
const initChart = () => {
  if (!chartRef.value) return
  myChart = echarts.init(chartRef.value)
  myChart.setOption({
    series: [
      {
        type: 'gauge',
        center: ['50%', '66%'],
        radius: '102%',
        startAngle: 200,
        endAngle: -20,
        min: 0,
        max: 100,
        splitNumber: 10,
        axisLine: {
          lineStyle: {
            width: 5,
            color: [
              [0.6, 'rgba(61, 222, 159, 0.92)'],
              [0.85, 'rgba(255, 211, 94, 0.92)'],
              [1, 'rgba(255, 108, 132, 0.92)'],
            ],
          },
        },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        pointer: { show: false },
        progress: { show: false },
        detail: { show: false },
        title: { show: false },
      },
      {
        type: 'gauge',
        center: ['50%', '66%'],
        radius: '95%',
        startAngle: 200,
        endAngle: -20,
        min: 0,
        max: 100,
        splitNumber: 10,
        itemStyle: {},
        splitLine: {
          distance: -10,
          length: 5,
          lineStyle: {
            color: 'rgba(255, 255, 255, 0.14)',
          },
        },
        axisLine: {
          lineStyle: {
            width: 14,
            color: [[1, 'rgba(23, 49, 74, 0.9)']],
          },
        },
        axisTick: {
          distance: -8,
          lineStyle: {
            color: 'rgba(255, 255, 255, 0.2)',
          },
        },
        axisLabel: {
          show: false,
        },
        pointer: {
          show: false,
        },
        progress: {
          show: true,
          width: 14,
          overlap: false,
          roundCap: true,
          itemStyle: {
            shadowBlur: 10,
            shadowColor: 'rgba(52, 200, 255, 0.35)',
          },
        },
        title: {
          fontSize: '0.8rem',
          color: '#b6d7ef',
          offsetCenter: ['0', '32%'],
        },
        detail: {
          width: 10,
          fontSize: '0.9rem',
          color: '#ecf7ff',
          formatter: '{value} %',
          offsetCenter: ['0', '-12%'],
        },
        data: transformData(props.data),
      },
    ],
  })
}
// 更新图表数据
const updateChart = () => {
  if (!myChart) return
  myChart?.setOption({
    series: [{}, { data: transformData(props.data) }],
  })
}

watch(
  () => props.data,
  () => {
    // console.log('gauge数据:', props.data)
    updateChart()
  },
)

onMounted(() => {
  initChart()
  window.addEventListener('resize', handleResize)
})

// 清理监听
onBeforeUnmount(() => {
  if (carouselInterval) {
    window.clearInterval(carouselInterval)
    carouselInterval = null
  }
  window.removeEventListener('resize', handleResize)
  myChart?.dispose()
  myChart = null
})
</script>

<style scoped>
.gaugecharts {
  width: 100%;
  height: 100%;
  margin: 0 auto;
  box-sizing: border-box;
  color: var(--text);
}
</style>
