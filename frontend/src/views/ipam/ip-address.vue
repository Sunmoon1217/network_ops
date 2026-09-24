<script setup lang="ts">
import PageLayout from '@/layout/PageLayout.vue'
import DataTable from '@/components/DataTable.vue'
import DataColumn from '@/components/DataColumn.vue'
import { TABLE_KEYS } from '@/constants/tableKeys'
import DataPagination from '@/components/DataPagination.vue'
import { useCrudApi } from '@/composables/useCrudApi'
import { statusTagType } from '@/composables/useTagType'
import { getIpAddresses, deleteIpAddress } from '@/api/ipam'

const router = useRouter()
const {
  data: ipList,
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
const filterStatus = ref('')

const statusOptions = [
  { label: '已使用', value: 'used' },
  { label: '预留', value: 'reserved' },
  { label: '可用', value: 'available' },
]

const fetchAll = () => fetchData(() => getIpAddresses(pageParams({ status: filterStatus.value || undefined })))

const remove = (row: any) => {
  handleDelete(row.ip_address, () => deleteIpAddress(row.id), fetchAll)
}

watch(filterStatus, resetAndFetch)
onMounted(fetchAll)
</script>

<template>
  <PageLayout title="IP 地址管理">
    <template #actions>
      <el-select v-model="filterStatus" placeholder="状态" clearable style="width: 110px">
        <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
      </el-select>
      <el-input v-model="search" placeholder="搜索 IP/描述" clearable style="width: 200px" />
      <el-button type="primary" @click="router.push('/ipam/ip-addresses/create')">新增 IP</el-button>
    </template>
    <div class="table-wrapper">
      <DataTable :table-key="TABLE_KEYS.ipamAddresses" :data="ipList" :loading="loading">
        <DataColumn prop="ip_address" label="IP 地址" width="150" sortable />
        <DataColumn prop="subnet_network" label="所属网段" width="140" />
        <DataColumn prop="status" label="状态" width="90">
          <template #default="{ row }"><el-tag :type="statusTagType(row.status)" size="small">{{ row.status }}</el-tag></template>
        </DataColumn>
        <DataColumn prop="device_hostname" label="关联设备" width="140" />
        <DataColumn prop="interface" label="接口" width="120" />
        <DataColumn prop="security_zone_name" label="安全区" width="100" />
        <DataColumn prop="description" label="描述" min-width="150" show-overflow-tooltip />
        <DataColumn label="操作" width="120" fixed="right" align="center">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="router.push(`/ipam/ip-addresses/${row.id}/edit`)">编辑</el-button>
            <el-button size="small" link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </DataColumn>
      </DataTable>
    </div>
    <DataPagination v-model:page="page" v-model:page-size="pageSize" :total="total" @change="refetch" />
  </PageLayout>
</template>

<style scoped>
.table-wrapper { flex: 1; min-height: 0; background: #fff; border-radius: 8px; overflow: hidden; }
</style>
