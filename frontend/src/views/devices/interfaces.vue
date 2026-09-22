<script setup lang="ts">
import PageLayout from '@/layout/PageLayout.vue'
import DataTable from '@/components/DataTable.vue'
import DataPagination from '@/components/DataPagination.vue'
import DeviceFilter from '@/components/DeviceFilter.vue'
import { useCrudApi } from '@/composables/useCrudApi'
import { modeTagType } from '@/composables/useTagType'
import { getInterfaces } from '@/api/interfaces'

const router = useRouter()
const { data: interfaces, loading, search, page, pageSize, total, fetchData, refetch, pageParams, resetAndFetch } =
  useCrudApi()
const filterDevice = ref<number | ''>('')
const filterMode = ref('')

const modeOptions = [
  { label: '三层接口', value: 'layer3' },
  { label: 'Access', value: 'access' },
  { label: 'Hybrid', value: 'hybrid' },
  { label: 'Trunk', value: 'trunk' },
]

const fetchAll = () =>
  fetchData(() =>
    getInterfaces(
      pageParams({
        device: filterDevice.value || undefined,
        mode: filterMode.value || undefined,
      })
    )
  )

watch(filterDevice, resetAndFetch)
watch(filterMode, resetAndFetch)
onMounted(fetchAll)
</script>

<template>
  <PageLayout title="接口管理">
    <template #actions>
      <DeviceFilter v-model="filterDevice" />
      <el-select v-model="filterMode" placeholder="接口模式" clearable style="width: 120px">
        <el-option v-for="m in modeOptions" :key="m.value" :label="m.label" :value="m.value" />
      </el-select>
      <el-input v-model="search" placeholder="搜索接口/IP/设备" clearable style="width: 200px" />
    </template>
    <div class="table-wrapper">
      <DataTable :data="interfaces" :loading="loading">
        <el-table-column prop="device_hostname" label="设备" width="150" sortable />
        <el-table-column prop="interface" label="接口" width="140" sortable />
        <el-table-column prop="mode" label="模式" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.mode" size="small" :type="modeTagType(row.mode)">{{ row.mode }}</el-tag>
            <span v-else style="color: #c0c4cc">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="ip_address" label="IP 地址" width="150" />
        <el-table-column prop="subnet_mask" label="子网掩码" width="130" />
        <el-table-column prop="vrf_name" label="VRF" width="120">
          <template #default="{ row }">
            <span v-if="row.vrf_name">{{ row.vrf_name }}</span>
            <span v-else style="color: #c0c4cc">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="enabled" label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? 'Up' : 'Down' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="150" show-overflow-tooltip />
        <el-table-column label="操作" width="80" fixed="right" align="center">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="router.push(`/devices/interfaces/${row.id}/edit`)">编辑</el-button>
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
