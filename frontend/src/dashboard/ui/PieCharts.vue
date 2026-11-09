<template>
  <div ref="chartRef" class="pie-charts"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
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

const currentIndex = ref(0)
const currentGroup = ref(props.data[0])
const chartRef = ref<HTMLDivElement | null>(null)
let myChart: echarts.ECharts | null = null
let carouselInterval: number | null = null

// 初始化图表
const initChart = () => {
  if (!chartRef.value) return
  myChart = echarts.init(chartRef.value)
  updateChart()
}
// 更新图表数据
const updateChart = () => {
  if (!myChart) return
  if (!currentGroup.value) return
  const option = {
    title: props.title
      ? {
          text: props.title,
          left: 'center',
          textStyle: {
            color: '#333',
            fontSize: 18,
          },
        }
      : '',
    tooltip: {
      trigger: 'item',
      formatter: '{b}<br/>{c} ({d}%)',
    },
    series: [
      {
        name: '数据',
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['50%', '50%'],
        label: {
          show: true,
          formatter: '{b}\n{c}',
          color: '#333',
        },
        itemStyle: {
          borderRadius: 10,
          shadowColor: '#000',
          shadowBlur: 10,
        },
        data: props.data || [],
        color: ['#5883ff', '#ff6b6b', '#4ecdc4', '#ff9f43', '#95e1d3'],
      },
    ],
    color: ['#5883ff'],
  }
  myChart.setOption(option)
}

// 轮播切换
const startCarousel = () => {
  carouselInterval = window.setInterval(() => {
    currentIndex.value = (currentIndex.value + 1) % props.data.length
    currentGroup.value = props.data[currentIndex.value]
    nextTick(() => {
      updateChart()
    })
  }, 5000) // 每5秒切换
}

onMounted(() => {
  initChart()
  startCarousel()
  window.addEventListener('resize', () => myChart?.resize())
})

// 清理监听
onBeforeUnmount(() => {
  window.removeEventListener('resize', () => myChart?.resize())
})
</script>

<style scoped>
.pie-charts {
  width: 100%;
  height: 100%;
  margin: 0 auto;
  box-sizing: border-box;
}
</style>
