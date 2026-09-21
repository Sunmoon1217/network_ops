<script setup lang="ts">
import VChart from 'vue-echarts'

defineProps<{
  option: any
  height?: string
}>()
</script>

<template>
  <el-card class="chart-card" shadow="hover">
    <v-chart :option="option" autoresize :style="{ height: height || '280px' }" />
  </el-card>
</template>

<style scoped>
.chart-card :deep(.el-card__body) { padding: 12px; }
</style>
