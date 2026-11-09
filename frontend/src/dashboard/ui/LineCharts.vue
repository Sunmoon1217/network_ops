<template>
  <div ref="chartRef" class="line-charts"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import echarts from './utils/echarts'
import type { TooltipComponentFormatterCallbackParams as LineParams } from 'echarts'
import type { LineChartsProps } from '@/types'

// 默认值
const props = withDefaults(defineProps<LineChartsProps>(), {
  data: () => [],
  xAxisData: () => [],
  yAxisName: '数值',
  title: '折线图',
  theme: 'light',
  height: '400px',
  width: '100%',
  loading: false,
})

const grouptitle = defineModel()
const groupdata = ref<any[]>()

const currentIndex = ref(0)
const currentGroup = ref(props.data[0])
const chartRef = ref<HTMLDivElement | null>(null)
let myChart: echarts.ECharts | null = null
let carouselInterval: number | null = null
let resizeObserver: ResizeObserver | null = null
const palette = ['#ffc0cb', '#008080', '#ffa500', '#ff00ff']
const handleResize = () => myChart?.resize()

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
  if (Array.isArray(currentGroup.value)) {
    groupdata.value = currentGroup.value
  } else {
    groupdata.value = currentGroup.value.data
    grouptitle.value = currentGroup.value.title
  }
  const option = {
    tooltip: {
      renderMode: 'html',
      appendToBody: true,
      confine: false,
      trigger: 'axis',
      formatter: (params: LineParams) => {
        // 自定义 tooltip 内容，确保显示所有系列
        if (!params || !Array.isArray(params) || params.length === 0) return ''

        const first = params[0]
        if (!first) return ''
        let res = `<b>${first.name}</b><br/>`

        params.forEach((param) => {
          // 类型安全访问：param 是 TooltipComponentFormatterCallbackParams 的
          res += `<span style="color:${param.color}">●</span> ${param.seriesName}: ${param.value?.toString().slice(0, 5)}<br/>`
        })

        return res
      },
    },
    legend: {
      show: true,
      data: groupdata.value.map((item) => item.name),
      orient: 'horizontal',
      top: 0,
      left: 'center',
      textStyle: {
        color: '#b6d7ef',
        fontSize: 11,
      },
    },
    grid: {
      left: 6,
      right: 18,
      top: 30,
      bottom: 4,
      containLabel: false,
    },
    roam: false,
    xAxis: {
      type: 'category',
      data: props.xAxisData,
      axisLabel: { color: '#9dbcd7', margin: 10, fontSize: 10 },
      axisTick: { show: false },
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
      axisLabel: { fontSize: 9, formatter: '{value}%', color: '#9dbcd7', margin: 8 },
      axisTick: { show: false },
      axisLine: { show: false },
      splitLine: {
        lineStyle: {
          color: 'rgba(111, 244, 255, 0.12)',
        },
      },
    },
    series: groupdata.value.map((item, index) => {
      const color = palette[index % palette.length] ?? '#34c8ff'

      return {
        name: item.name,
        type: 'line',
        smooth: true,
        data: item.value.map((a: number) => (a === -1 ? null : a)) || [],
        connectNulls: true,
        symbol: 'circle',
        symbolSize: 2,
        lineStyle: {
          color,
          width: 2,
        },
        itemStyle: {
          color,
          borderColor: '#e8f8ff',
          borderWidth: 1,
        },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: color + '66' },
            { offset: 1, color: color + '0d' },
          ]),
        },
      }
    }),
    color: palette,
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
  window.addEventListener('resize', handleResize)
  if (chartRef.value) {
    resizeObserver = new ResizeObserver(() => {
      myChart?.resize()
    })
    resizeObserver.observe(chartRef.value)
  }
})

watch(
  () => [props.data, props.xAxisData],
  () => {
    if (!props.data.length) return
    if (!currentGroup.value) {
      currentGroup.value = props.data[0]
    }
    updateChart()
    handleResize()
  },
  { deep: true },
)

// 清理监听
onBeforeUnmount(() => {
  if (carouselInterval) {
    window.clearInterval(carouselInterval)
    carouselInterval = null
  }
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
