<script setup lang="ts">
import PageLayout from '@/ui/PageLayout.vue'
import api from '@/api/index'

const domain = ref('')
const recordType = ref('A')
const loading = ref(false)
const results = ref<any[]>([])
const error = ref('')

const recordTypes = ['A', 'AAAA', 'CNAME', 'MX', 'TXT', 'NS', 'SRV']

async function query() {
  if (!domain.value.trim()) { error.value = '请输入域名'; return }
  loading.value = true
  error.value = ''
  results.value = []
  try {
    const resp = await api.get('/api/trace/dns-query/', {
      params: { domain: domain.value.trim(), type: recordType.value },
    })
    results.value = resp.data.records || []
    if (resp.data.error) error.value = resp.data.error
    if (results.value.length === 0 && !error.value) error.value = '无解析结果'
  } catch (e: any) {
    error.value = e.response?.data?.error || '查询失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <PageLayout title="DNS 查询">
    <template #actions>
      <el-input v-model="domain" placeholder="域名 (如 example.com)" style="width: 240px" @keyup.enter="query" />
      <el-select v-model="recordType" style="width: 100px">
        <el-option v-for="t in recordTypes" :key="t" :label="t" :value="t" />
      </el-select>
      <el-button type="primary" :loading="loading" @click="query">查询</el-button>
    </template>
    <div class="table-wrapper">
      <el-alert v-if="error" type="error" :closable="false" style="margin-bottom: 12px;">{{ error }}</el-alert>
      <DataTable v-if="results.length" :data="results" :loading="loading">
        <el-table-column prop="type" label="类型" width="80" />
        <el-table-column prop="name" label="域名" width="250" />
        <el-table-column prop="value" label="值" min-width="250" />
        <el-table-column prop="ttl" label="TTL" width="80" />
      </DataTable>
      <el-empty v-if="!loading && !error && results.length === 0 && domain" description="无解析结果" />
    </div>
  </PageLayout>
</template>

<style scoped>
.table-wrapper { flex: 1; min-height: 0; background: #fff; border-radius: 8px; padding: 16px; overflow: auto; }
</style>
