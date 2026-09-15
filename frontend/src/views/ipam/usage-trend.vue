<script setup lang="ts">
import PageLayout from '@/ui/PageLayout.vue'
import ChartCard from '@/ui/ChartCard.vue'
import { lineOpt } from '@/composables/useEcharts'
import api from '@/api/index'
import { getSubnets } from '@/api/ipam'

const subnets = ref<any[]>([])
const selectedSubnet = ref<number | ''>('')
const loading = ref(false)
const logs = ref<any[]>([])

const chartOption = computed(() => {
  if (!logs.value.length) return null
  const sorted = [...logs.value].reverse()
  return lineOpt(
    'IP 使用率趋势',
    sorted.map(l => new Date(l.recorded_at).toLocaleDateString()),
    sorted.map(l => l.utilization),
    '%',
  )
})

async function fetchSubnets() {
  try {
    const res = await getSubnets()
    subnets.value = res.data.results || res.data || []
  } catch { /* ignore */ }
}

async function fetchLogs() {
  if (!selectedSubnet.value) { logs.value = []; return }
  loading.value = true
  try {
    const resp = await api.get('/api/assets/subnet-usage-logs/', { params: { subnet: selectedSubnet.value } })
    logs.value = resp.data.results || resp.data || []
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

watch(selectedSubnet, fetchLogs)
onMounted(fetchSubnets)
</script>

<template>
  <PageLayout title="IP 使用率趋势">
    <template #actions>
      <el-select v-model="selectedSubnet" placeholder="选择网段" clearable filterable style="width: 240px">
        <el-option v-for="s in subnets" :key="s.id" :label="s.network" :value="s.id" />
      </el-select>
    </template>
    <div v-loading="loading" class="trend-body">
      <el-empty v-if="!selectedSubnet" description="请选择一个网段查看使用率趋势" />
      <el-empty v-else-if="!logs.length && !loading" description="暂无历史数据" />
      <ChartCard v-else-if="chartOption" :option="chartOption" height="400px" />
    </div>
  </PageLayout>
</template>

<style scoped>
.trend-body { flex: 1; min-height: 0; background: #fff; border-radius: 8px; padding: 16px; }
</style>
