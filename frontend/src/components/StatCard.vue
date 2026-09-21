<script setup lang="ts">
defineProps<{
  label: string
  value: number | string
  color?: string
  icon?: string
}>()
</script>

<template>
  <el-card class="stat-card" shadow="hover">
    <span v-if="icon" class="stat-icon">{{ icon }}</span>
    <div class="stat-body">
      <div class="stat-value" :style="color ? { color } : {}">{{ value }}</div>
      <div class="stat-label">{{ label }}</div>
    </div>
  </el-card>
</template>

<style scoped>
.stat-card { display: flex; align-items: center; }
.stat-card :deep(.el-card__body) { display: flex; align-items: center; gap: 10px; padding: 14px 16px; width: 100%; }
.stat-icon { font-size: 24px; }
.stat-body { display: flex; flex-direction: column; }
.stat-value { font-size: 26px; font-weight: 700; font-family: 'SF Mono', 'Cascadia Code', monospace; line-height: 1.2; }
.stat-label { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 2px; }
</style>
