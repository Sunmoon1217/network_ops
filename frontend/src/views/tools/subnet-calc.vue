<script setup lang="ts">
import PageLayout from '@/ui/PageLayout.vue'

const input = ref('10.0.0.0/24')
const splitCount = ref<number | null>(null)
const results = ref<any[]>([])
const error = ref('')

function calculate() {
  error.value = ''
  results.value = []
  try {
    const parts = input.value.trim().split('/')
    if (parts.length !== 2) { error.value = '格式: IP/CIDR (如 10.0.0.0/24)'; return }
    const ip = parts[0]
    const prefix = parseInt(parts[1])
    if (isNaN(prefix) || prefix < 0 || prefix > 32) { error.value = 'CIDR 前缀范围: 0-32'; return }

    const ipNum = ipToNum(ip)
    if (ipNum === null) { error.value = '无效 IP 地址'; return }

    const mask = prefix === 0 ? 0 : (~0 << (32 - prefix)) >>> 0
    const network = (ipNum & mask) >>> 0
    const broadcast = (network | ~mask) >>> 0
    const totalHosts = broadcast - network + 1
    const usable = totalHosts >= 2 ? totalHosts - 2 : totalHosts

    results.value.push({
      label: '网络地址', value: numToIp(network),
    }, {
      label: '广播地址', value: numToIp(broadcast),
    }, {
      label: '子网掩码', value: numToIp(mask),
    }, {
      label: 'CIDR 前缀', value: `/${prefix}`,
    }, {
      label: '总 IP 数', value: totalHosts.toLocaleString(),
    }, {
      label: '可用 IP 数', value: usable.toLocaleString(),
    }, {
      label: 'IP 范围', value: totalHosts >= 2 ? `${numToIp(network + 1)} - ${numToIp(broadcast - 1)}` : numToIp(network),
    })

    // 子网拆分
    if (splitCount.value && splitCount.value > 1) {
      const newPrefix = prefix + Math.ceil(Math.log2(splitCount.value))
      if (newPrefix > 32) { error.value = '拆分数超出 CIDR 范围'; return }
      const blockSize = Math.pow(2, 32 - newPrefix)
      const splits = []
      for (let i = 0; i < Math.min(splitCount.value, 16); i++) {
        const subNetwork = (network + i * blockSize) >>> 0
        const subBroadcast = (subNetwork + blockSize - 1) >>> 0
        splits.push({
          cidr: `${numToIp(subNetwork)}/${newPrefix}`,
          range: `${numToIp(subNetwork + 1)} - ${numToIp(subBroadcast - 1)}`,
          hosts: (blockSize - 2).toLocaleString(),
        })
      }
      results.value.push({ label: '', value: '', isDivider: true })
      results.value.push({ label: `拆分为 ${splitCount.value} 个 /${newPrefix} 子网`, value: '', isHeader: true })
      for (const s of splits) {
        results.value.push({ label: s.cidr, value: `${s.range} (${s.hosts} 可用)`, isSplit: true })
      }
    }
  } catch (e: any) {
    error.value = e.message || '计算错误'
  }
}

function ipToNum(ip: string): number | null {
  const parts = ip.split('.')
  if (parts.length !== 4) return null
  let num = 0
  for (const p of parts) {
    const n = parseInt(p)
    if (isNaN(n) || n < 0 || n > 255) return null
    num = (num << 8 | n) >>> 0
  }
  return num
}

function numToIp(num: number): string {
  return [(num >>> 24) & 0xff, (num >>> 16) & 0xff, (num >>> 8) & 0xff, num & 0xff].join('.')
}

onMounted(calculate)
</script>

<template>
  <PageLayout title="子网计算器">
    <template #actions>
      <el-input v-model="input" placeholder="IP/CIDR (如 10.0.0.0/24)" style="width: 200px" @keyup.enter="calculate" />
      <el-input-number v-model="splitCount" :min="2" :max="256" placeholder="拆分数" controls-position="right" style="width: 120px" />
      <el-button type="primary" @click="calculate">计算</el-button>
    </template>

    <div class="calc-body">
      <el-alert v-if="error" type="error" :closable="false" style="margin-bottom: 12px;">{{ error }}</el-alert>

      <div v-if="results.length" class="result-grid">
        <template v-for="item in results" :key="item.label">
          <div v-if="item.isDivider" class="divider" />
          <div v-else-if="item.isHeader" class="result-header">{{ item.label }}</div>
          <template v-else>
            <div class="result-label" :class="{ 'split-label': item.isSplit }">{{ item.label }}</div>
            <div class="result-value" :class="{ 'split-value': item.isSplit }">{{ item.value }}</div>
          </template>
        </template>
      </div>
    </div>
  </PageLayout>
</template>

<style scoped>
.calc-body { background: #fff; border-radius: 8px; padding: 24px; max-width: 640px; }
.result-grid { display: grid; grid-template-columns: 140px 1fr; gap: 8px 16px; }
.result-label { font-size: 13px; color: var(--el-text-color-secondary); font-family: monospace; }
.result-value { font-size: 13px; font-weight: 600; font-family: monospace; }
.divider { grid-column: 1 / -1; height: 1px; background: var(--el-border-color-lighter); margin: 8px 0; }
.result-header { grid-column: 1 / -1; font-size: 13px; font-weight: 600; color: var(--el-color-primary); }
.split-label { font-size: 12px; }
.split-value { font-size: 12px; font-weight: 400; }
</style>
