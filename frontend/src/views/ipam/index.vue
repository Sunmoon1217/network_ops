<script setup lang="ts">
import PageLayout from '@/layout/PageLayout.vue'
import DataTable from '@/components/DataTable.vue'
import DataPagination from '@/components/DataPagination.vue'
import { useCrudApi } from '@/composables/useCrudApi'
import { getSubnets, deleteSubnet } from '@/api/ipam'
import { fetchAllPages } from '@/utils/fetchAllPages'

const router = useRouter()
const {
  data: subnets,
  loading,
  search,
  page,
  pageSize,
  total,
  fetchData,
  refetch,
  pageParams,
  resetAndFetch,
  handleDelete,
} = useCrudApi()
const filterTag = ref<number | ''>('')
const tags = ref<any[]>([])

const fetchAll = () => fetchData(() => getSubnets(pageParams({ tag: filterTag.value || undefined })))

const remove = (row: any) => {
  handleDelete(row.network, () => deleteSubnet(row.id), fetchAll)
}

// 标签下拉选项独立拉取全量，避免受网段列表分页影响
const loadTags = async () => {
  try {
    tags.value = await fetchAllPages('/api/assets/tags/', { ordering: 'name' })
  } catch {
    /* 选项加载失败不影响主列表 */
  }
}

watch(filterTag, resetAndFetch)
onMounted(() => {
  fetchAll()
  loadTags()
})
</script>

<template>
  <PageLayout title="IP 管理">
    <template #actions>
      <el-select v-model="filterTag" placeholder="标签" clearable style="width: 120px">
        <el-option v-for="t in tags" :key="t.id" :label="t.name" :value="t.id" />
      </el-select>
      <el-input v-model="search" placeholder="搜索网段/描述" clearable style="width: 200px" />
      <el-button type="primary" @click="router.push('/ipam/subnets/create')">新增网段</el-button>
    </template>
    <div class="table-wrapper">
      <DataTable :data="subnets" :loading="loading">
        <el-table-column prop="network" label="网段" width="160" sortable />
        <el-table-column prop="gateway" label="网关" width="140" />
        <el-table-column prop="vlan" label="VLAN" width="80" />
        <el-table-column prop="tag_names" label="标签" width="150">
          <template #default="{ row }"><el-tag v-for="t in row.tag_names" :key="t" size="small" style="margin-right: 4px">{{ t }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="total_ips" label="总IP" width="80" />
        <el-table-column prop="used_ips" label="已用" width="70" />
        <el-table-column prop="utilization" label="使用率" width="90">
          <template #default="{ row }"><el-progress :percentage="row.utilization || 0" :stroke-width="14" :text-inside="true" style="width: 70px" /></template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="150" show-overflow-tooltip />
        <el-table-column label="操作" width="120" fixed="right" align="center">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="router.push(`/ipam/subnets/${row.id}/edit`)">编辑</el-button>
            <el-button size="small" link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </DataTable>
    </div>
    <DataPagination v-model:page="page" v-model:page-size="pageSize" :total="total" @change="refetch" />
  </PageLayout>
</template>

<style scoped>
.table-wrapper { flex: 1; min-height: 0; background: #fff; border-radius: 8px; overflow: hidden; }
</style>
