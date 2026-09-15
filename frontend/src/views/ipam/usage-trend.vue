<script setup lang="ts">
import PageLayout from '@/ui/PageLayout.vue'
import ChartCard from '@/ui/ChartCard.vue'
import { lineOpt } from '@/composables/useEcharts'
import { fetchAllPages } from '@/utils/fetchAllPages'

const subnets = ref<any[]>([])
const selectedSubnet = ref<number | ''>('')
const loading = ref(false)
const logs = ref<any[]>([])

const chartOption = computed(() => {
  if (!logs.value.length) return null
  // 接口按 ordering=recorded_at 返回升序，这里再兜底排序一次，确保时间轴正序
  const sorted = [...logs.value].sort(
    (a, b) => new Date(a.recorded_at).getTime() - new Date(b.recorded_at).getTime(),
  )
  return lineOpt(
    'IP 使用率趋势',
    sorted.map(l => new Date(l.recorded_at).toLocaleDateString()),
    sorted.map(l => l.utilization),
    '%',
  )
})

async function fetchSubnets() {
  try {
    // 下拉选项必须完整，使用循环拉全量
    subnets.value = await fetchAllPages('/api/assets/subnets/', { ordering: 'network' })
  } catch { /* ignore */ }
}

async function fetchLogs() {
  if (!selectedSubnet.value) { logs.value = []; return }
  loading.value = true
  try {
    // 趋势图需要完整时间序列，同样循环拉全量
    logs.value = await fetchAllPages('/api/assets/subnet-usage-logs/', {
      subnet: selectedSubnet.value,
      ordering: 'recorded_at',
    })
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
