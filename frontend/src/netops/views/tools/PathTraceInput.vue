<script setup lang="ts">
defineProps<{
  srcIp: string
  dstIp: string
  dstPort: string
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'update:srcIp', value: string): void
  (e: 'update:dstIp', value: string): void
  (e: 'update:dstPort', value: string): void
  (e: 'trace'): void
}>()
</script>

<template>
  <div class="trace-input-bar">
    <div class="input-title">路径追踪</div>
    <div class="input-fields">
      <el-input :model-value="srcIp" placeholder="源地址" style="width: 160px" @update:model-value="emit('update:srcIp', $event)" @keyup.enter="emit('trace')" />
      <span class="arrow">→</span>
      <el-input :model-value="dstIp" placeholder="目的地址" style="width: 160px" @update:model-value="emit('update:dstIp', $event)" @keyup.enter="emit('trace')" />
      <el-input :model-value="dstPort" placeholder="端口" style="width: 90px" @update:model-value="emit('update:dstPort', $event)" @keyup.enter="emit('trace')" />
      <el-button type="primary" :loading="loading" @click="emit('trace')">追踪</el-button>
    </div>
  </div>
</template>

<style scoped>
.trace-input-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-radius: 10px;
  background: rgba(52, 200, 255, 0.04);
  border: 1px solid rgba(52, 200, 255, 0.15);
  flex-shrink: 0;
}
.input-title { font-size: 14px; font-weight: 600; color: var(--el-text-color-primary); }
.input-fields { display: flex; align-items: center; gap: 10px; }
.arrow { font-size: 16px; color: #34c8ff; }
</style>
