<script setup lang="ts">
import PageLayout from '@/ui/PageLayout.vue'
import DataTable from '@/ui/DataTable.vue'
import { useCrudApi } from '@/composables/useCrudApi'
import api from '@/api/index'

const { data: vlans, loading, search, filteredData, fetchData } = useCrudApi(['vid', 'name', 'description'])

onMounted(() => fetchData(() => api.get('/api/assets/vlans/')))
</script>

<template>
  <PageLayout title="VLAN 管理">
    <template #actions>
      <el-input v-model="search" placeholder="搜索 VID/名称" clearable style="width: 200px" />
    </template>
    <div class="table-wrapper">
      <DataTable :data="filteredData" :loading="loading">
        <el-table-column prop="vid" label="VID" width="100" sortable />
        <el-table-column prop="name" label="名称" width="200" sortable />
        <el-table-column prop="description" label="描述" min-width="250" show-overflow-tooltip />
      </DataTable>
    </div>
  </PageLayout>
</template>

<style scoped>
.table-wrapper { flex: 1; min-height: 0; background: #fff; border-radius: 8px; overflow: hidden; }
</style>
