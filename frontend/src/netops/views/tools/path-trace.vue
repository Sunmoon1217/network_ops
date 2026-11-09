<script setup lang="ts">
import PathTraceInput from './PathTraceInput.vue'
import PathTraceFlowchart from './PathTraceFlowchart.vue'
import { usePathTrace } from './usePathTrace'

const { srcIp, dstIp, dstPort, loading, result, error, handleTrace } = usePathTrace()
</script>

<template>
  <div class="trace-page">
    <PathTraceInput
      v-model:src-ip="srcIp"
      v-model:dst-ip="dstIp"
      v-model:dst-port="dstPort"
      :loading="loading"
      @trace="handleTrace"
    />
    <el-alert v-if="error" type="error" :closable="false" style="margin: 12px 0;">{{ error }}</el-alert>
    <div v-loading="loading" style="flex: 1; min-height: 0;">
      <PathTraceFlowchart v-if="result && !result.error" :result="result" :src-ip="srcIp" />
    </div>
  </div>
</template>

<style scoped>
.trace-page { height: 100%; display: flex; flex-direction: column; padding: 16px; gap: 12px; }
</style>
