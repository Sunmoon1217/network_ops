<template>
  <div ref="chartRef" class="gaugecharts"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import echarts from './utils/echarts'
import type { GaugeChartsProps } from '@/types'

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
        },
        detail: {
          width: 10,
          fontSize: '0.8rem',
          color: '#ecf7ff',
          formatter: '{value} %',
        },
        data: props.data,
      },
    ],
  })
}
// 更新图表数据
const updateChart = () => {
  if (!myChart) return
  myChart?.setOption({
    series: [{}, { data: props.data }],
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
