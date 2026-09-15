<script setup lang="ts">
import PageLayout from '@/ui/PageLayout.vue'
import ChartCard from '@/ui/ChartCard.vue'
import { pieOpt } from '@/composables/useEcharts'
import api from '@/api/index'

const domain = ref('')
const domains = ref('')
const recordType = ref('A')
const mode = ref<'single' | 'batch'>('single')
const dnsServers = ref(['', '', ''])
const loading = ref(false)
const error = ref('')
const results = ref<any[]>([])
const batchStats = ref<any[]>([])
const batchDetails = ref<any[]>([])

const recordTypes = ['A', 'AAAA', 'CNAME', 'MX', 'TXT', 'NS', 'SRV', 'PTR']

async function query() {
  error.value = ''
  results.value = []
  batchStats.value = []
  batchDetails.value = []

  if (mode.value === 'single') {
    if (!domain.value.trim()) { error.value = '请输入域名'; return }
    await querySingle(domain.value.trim())
  } else {
    const lines = domains.value.split('\n').map(l => l.trim()).filter(Boolean)
    if (!lines.length) { error.value = '请输入至少一个域名'; return }
    await queryBatch(lines)
  }
}

async function querySingle(name: string) {
  loading.value = true
  const servers = dnsServers.value.filter(s => s.trim())
  try {
    if (servers.length > 0) {
      const promises = servers.map(async server => {
        const t0 = performance.now()
        try {
          const r = await api.get('/api/trace/dns-query/', { params: { domain: name, type: recordType.value, server: server.trim() } })
          return { server: server.trim(), records: r.data.records || [], error: r.data.error, time: Math.round(performance.now() - t0) }
        } catch (e: any) {
          return { server: server.trim(), records: [], error: e.response?.data?.error || '查询失败', time: Math.round(performance.now() - t0) }
        }
      })
      const responses = await Promise.all(promises)
      results.value = responses.map(r => ({ ...r }))
    } else {
      const t0 = performance.now()
      const resp = await api.get('/api/trace/dns-query/', { params: { domain: name, type: recordType.value } })
      const time = Math.round(performance.now() - t0)
      results.value = [{ server: '默认', records: resp.data.records || [], error: resp.data.error, time }]
      if (resp.data.error && !resp.data.records?.length) error.value = resp.data.error
    }
  } catch (e: any) {
    error.value = e.response?.data?.error || '查询失败'
  } finally {
    loading.value = false
  }
}

async function queryBatch(names: string[]) {
  loading.value = true
  const servers = dnsServers.value.filter(s => s.trim())
  const targetServers = servers.length > 0 ? servers : ['默认']
  const successCounts: Record<string, number> = {}
  let total = 0
  let success = 0

  try {
    const batchSize = 5
    for (let i = 0; i < names.length; i += batchSize) {
      const batch = names.slice(i, i + batchSize)
      const promises = batch.map(async name => {
        for (const server of targetServers) {
          const params: Record<string, any> = { domain: name, type: recordType.value }
          if (server !== '默认') params.server = server
          const t0 = performance.now()
          try {
            const r = await api.get('/api/trace/dns-query/', { params })
            const time = Math.round(performance.now() - t0)
            const records = r.data.records || []
            if (records.length > 0) {
              success++
              for (const rec of records) successCounts[rec.value] = (successCounts[rec.value] || 0) + 1
            }
            total++
            batchDetails.value.push({ domain: name, server, records, error: r.data.error, time })
          } catch (e: any) {
            total++
            batchDetails.value.push({ domain: name, server, records: [], error: e.response?.data?.error || '失败', time: Math.round(performance.now() - t0) })
          }
        }
      })
      await Promise.all(promises)
    }

    batchStats.value = [
      { label: '查询数', value: total },
      { label: '成功', value: success },
      { label: '失败', value: total - success },
      { label: '成功率', value: total ? `${Math.round(success / total * 100)}%` : '0%' },
    ]

    const pieData = Object.entries(successCounts).map(([name, value]) => ({ name, value }))
    if (total - success > 0) pieData.push({ name: '失败', value: total - success })
    if (pieData.length > 0) {
      results.value = [{ chart: pieOpt(`${recordType.value} 解析结果分布`, pieData) }]
    }
  } catch (e: any) {
    error.value = e.message || '批量查询失败'
  } finally {
    loading.value = false
  }
}

// 检查两个服务器的结果是否一致
function isSameResult(a: any[], b: any[]): boolean {
  if (a.length !== b.length) return false
  const va = a.map(r => r.value).sort()
  const vb = b.map(r => r.value).sort()
  return va.every((v, i) => v === vb[i])
}
</script>

<template>
  <PageLayout title="DNS 查询">
    <template #actions>
      <el-segmented v-model="mode" :options="[{ label: '单次查询', value: 'single' }, { label: '批量解析', value: 'batch' }]" size="small" />
    </template>

    <!-- 查询输入区 -->
    <div class="query-bar">
      <el-input v-if="mode === 'single'" v-model="domain" placeholder="域名" style="width: 200px" @keyup.enter="query" />
      <el-select v-model="recordType" style="width: 100px">
        <el-option v-for="t in recordTypes" :key="t" :label="t" :value="t" />
      </el-select>
      <el-button type="primary" :loading="loading" @click="query">查询</el-button>
    </div>

    <!-- DNS 服务器输入 -->
    <div class="server-bar">
      <span class="server-label">DNS 服务器（可选）:</span>
      <el-input v-model="dnsServers[0]" placeholder="8.8.8.8" clearable style="width: 140px" />
      <el-input v-model="dnsServers[1]" placeholder="114.114.114.114" clearable style="width: 140px" />
      <el-input v-model="dnsServers[2]" placeholder="1.1.1.1" clearable style="width: 140px" />
    </div>

    <!-- 批量输入 -->
    <div v-if="mode === 'batch'" class="batch-bar">
      <el-input v-model="domains" type="textarea" :rows="6" placeholder="每行一个域名&#10;example.com&#10;google.com&#10;github.com" />
    </div>

    <div class="result-area">
      <el-alert v-if="error" type="error" :closable="false" style="margin-bottom: 12px;">{{ error }}</el-alert>

      <!-- 单次查询：左右对比 -->
      <template v-if="mode === 'single' && results.length">
        <div class="compare-grid" :style="{ gridTemplateColumns: `repeat(${results.length}, 1fr)` }">
          <div v-for="(group, idx) in results" :key="idx" class="compare-col">
            <div class="compare-header">
              <span class="server-name">{{ group.server }}</span>
              <div class="header-right">
                <span class="response-time">{{ group.time }}ms</span>
                <el-tag v-if="!group.error" type="success" size="small">{{ group.records.length }} 条</el-tag>
                <el-tag v-else type="danger" size="small">失败</el-tag>
              </div>
            </div>
            <el-alert v-if="group.error" type="warning" :closable="false" style="margin: 0 0 8px 0;">{{ group.error }}</el-alert>
            <el-table v-if="group.records.length" :data="group.records" stripe size="small" style="width: 100%">
              <el-table-column prop="type" label="类型" width="70" />
              <el-table-column prop="value" label="值" min-width="140" />
              <el-table-column prop="ttl" label="TTL" width="60" />
            </el-table>
          </div>
        </div>

        <!-- 差异提示（多服务器时） -->
        <div v-if="results.length >= 2 && results.every(r => !r.error)" class="diff-banner">
          <el-tag v-if="isSameResult(results[0].records, results[1].records)" type="success" size="default">
            ✓ 结果一致
          </el-tag>
          <el-tag v-else type="warning" size="default">
            ✗ 结果不同
          </el-tag>
        </div>
      </template>

      <!-- 批量统计 -->
      <template v-if="mode === 'batch' && batchStats.length">
        <div class="stats-row">
          <el-card v-for="s in batchStats" :key="s.label" class="stat-card" shadow="hover">
            <div class="stat-value">{{ s.value }}</div>
            <div class="stat-label">{{ s.label }}</div>
          </el-card>
        </div>
        <ChartCard v-if="results.length && results[0].chart" :option="results[0].chart" height="300px" />

        <!-- 批量明细表格 -->
        <div v-if="batchDetails.length" class="batch-table-wrap">
          <el-table :data="batchDetails" stripe border size="small" style="width: 100%">
            <el-table-column prop="domain" label="域名" width="200" sortable />
            <el-table-column prop="server" label="DNS" width="130" />
            <el-table-column label="结果" min-width="200">
              <template #default="{ row }">
                <template v-if="row.records.length">
                  <el-tag v-for="r in row.records" :key="r.value" size="small" style="margin: 2px;">{{ r.value }}</el-tag>
                </template>
                <span v-else style="color: var(--el-text-color-placeholder);">{{ row.error || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="time" label="耗时" width="80" sortable>
              <template #default="{ row }">{{ row.time }}ms</template>
            </el-table-column>
          </el-table>
        </div>
      </template>

      <el-empty v-if="!loading && !error && !results.length && !batchStats.length" description="输入域名开始查询" />
    </div>
  </PageLayout>
</template>

<style scoped>
.query-bar { display: flex; gap: 10px; align-items: center; margin-bottom: 12px; flex-shrink: 0; }
.server-bar { display: flex; gap: 10px; align-items: center; margin-bottom: 12px; flex-shrink: 0; }
.server-label { font-size: 12px; color: var(--el-text-color-secondary); flex-shrink: 0; }
.batch-bar { margin-bottom: 12px; flex-shrink: 0; }
.result-area { flex: 1; min-height: 0; overflow: auto; }
.compare-grid { display: grid; gap: 16px; margin-bottom: 16px; }
.compare-col { background: #fff; border-radius: 8px; border: 1px solid var(--el-border-color-lighter); overflow: hidden; }
.compare-header { display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; background: var(--el-fill-color-light); border-bottom: 1px solid var(--el-border-color-lighter); }
.server-name { font-size: 13px; font-weight: 600; color: var(--el-color-primary); }
.header-right { display: flex; align-items: center; gap: 8px; }
.response-time { font-size: 12px; color: var(--el-text-color-secondary); font-family: monospace; }
.diff-banner { text-align: center; margin-top: 12px; }
.stats-row { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.stat-card { flex: 1; min-width: 100px; text-align: center; }
.stat-card :deep(.el-card__body) { padding: 14px 10px; }
.stat-value { font-size: 24px; font-weight: 700; font-family: monospace; }
.stat-label { font-size: 12px; color: var(--el-text-color-secondary); }
.batch-table-wrap { margin-top: 16px; }
</style>
