<script setup lang="ts">
import PageLayout from '@/ui/PageLayout.vue'
import DataTable from '@/ui/DataTable.vue'
import DataPagination from '@/ui/DataPagination.vue'
import { useCrudApi } from '@/composables/useCrudApi'
import { getTags, deleteTag } from '@/api/ipam'

const router = useRouter()
const { data: tags, loading, page, pageSize, total, fetchData, refetch, pageParams, handleDelete } = useCrudApi()

const fetchAll = () => fetchData(() => getTags(pageParams()))

const remove = (row: any) => {
  handleDelete(row.name, () => deleteTag(row.id), fetchAll)
}

onMounted(fetchAll)
</script>

<template>
  <PageLayout title="标签管理">
    <template #actions>
      <el-button type="primary" @click="router.push('/ipam/tags/create')">新增标签</el-button>
    </template>
    <div class="table-wrapper">
      <DataTable :data="tags" :loading="loading">
        <el-table-column prop="name" label="标签名称" width="200" sortable />
        <el-table-column prop="color" label="颜色" width="100">
          <template #default="{ row }">
            <span :style="{ display: 'inline-block', width: '16px', height: '16px', borderRadius: '3px', background: row.color, verticalAlign: 'middle', marginRight: '6px' }" />
            {{ row.color }}
          </template>
        </el-table-column>
        <el-table-column prop="subnet_count" label="关联网段" width="100" />
        <el-table-column label="操作" width="120" fixed="right" align="center">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="router.push(`/ipam/tags/${row.id}/edit`)">编辑</el-button>
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
