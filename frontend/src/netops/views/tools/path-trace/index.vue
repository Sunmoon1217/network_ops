<script setup lang="ts">
import Input from './Input.vue'
import Flowchart from './Flowchart.vue'
import { usePathTrace } from './useTrace'

const { srcIp, dstIp, dstPort, loading, result, error, handleTrace } = usePathTrace()
</script>

<template>
  <div class="trace-page">
    <Input
      v-model:src-ip="srcIp"
      v-model:dst-ip="dstIp"
      v-model:dst-port="dstPort"
      :loading="loading"
      @trace="handleTrace"
    />
    <el-alert v-if="error" type="error" :closable="false" style="margin: 12px 0;">{{ error }}</el-alert>
    <div v-loading="loading" style="flex: 1; min-height: 0;">
      <Flowchart v-if="result && !result.error" :result="result" :src-ip="srcIp" />
    </div>
  </div>
</template>

<style scoped>
.trace-page { height: 100%; display: flex; flex-direction: column; padding: 16px; gap: 12px; }
</style>
