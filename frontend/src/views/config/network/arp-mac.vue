<script setup lang="ts">
import PageLayout from '@/ui/PageLayout.vue'
import DataTable from '@/ui/DataTable.vue'
import DataPagination from '@/ui/DataPagination.vue'
import DeviceFilter from '@/ui/DeviceFilter.vue'
import { useCrudApi } from '@/composables/useCrudApi'
import { fetchAllPages } from '@/utils/fetchAllPages'
import api from '@/api/index'

const { data: entries, loading, search, page, pageSize, total, fetchData, refetch, pageParams, resetAndFetch } =
  useCrudApi()
const filterDevice = ref<number | ''>('')
const filterVlan = ref('')
const filterType = ref('')

// VLAN 下拉选项来自 VLAN 表（独立拉取，避免受 ARP 表分页影响）
const vlanOptions = ref<string[]>([])

const loadVlanOptions = async () => {
  try {
    const list = await fetchAllPages('/api/assets/vlans/', { ordering: 'vid' })
    const vids = list.map((v: any) => String(v.vid)).filter(Boolean)
    vlanOptions.value = Array.from(new Set(vids)).sort((a, b) => Number(a) - Number(b))
  } catch {
    /* 选项加载失败不影响主列表 */
  }
}

const fetchAll = () =>
  fetchData(() =>
    api.get('/api/assets/arp-mac/', {
      params: pageParams({
        device: filterDevice.value || undefined,
        vlan: filterVlan.value || undefined,
        arp_type: filterType.value || undefined,
      }),
    })
  )

const statusTag = (s: string) => {
  const map: Record<string, string> = { normal: 'success', aging: 'warning', conflict: 'danger' }
  return (map[s] || 'info') as any
}

const statusLabel: Record<string, string> = { normal: '正常', aging: '老化中', conflict: '冲突' }

watch(filterDevice, resetAndFetch)
watch(filterVlan, resetAndFetch)
watch(filterType, resetAndFetch)
onMounted(() => {
  fetchAll()
  loadVlanOptions()
})
</script>

<template>
  <PageLayout title="ARP / MAC 表">
    <template #actions>
      <DeviceFilter v-model="filterDevice" />
      <el-select v-model="filterVlan" placeholder="VLAN" clearable style="width: 120px">
        <el-option v-for="v in vlanOptions" :key="v" :label="v" :value="v" />
      </el-select>
      <el-select v-model="filterType" placeholder="ARP 类型" clearable style="width: 110px">
        <el-option label="动态" value="dynamic" />
        <el-option label="静态" value="static" />
      </el-select>
      <el-input v-model="search" placeholder="搜索 IP/MAC/设备/接口" clearable style="width: 220px" />
    </template>
    <div class="table-wrapper">
      <DataTable :data="entries" :loading="loading">
        <el-table-column prop="device_hostname" label="设备" width="150" sortable />
        <el-table-column prop="vlan" label="VLAN" width="100" sortable />
        <el-table-column prop="interface" label="接口" width="200" show-overflow-tooltip />
        <el-table-column prop="ip_address" label="IP 地址" width="150" sortable />
        <el-table-column prop="mac_address" label="MAC 地址" width="170" sortable />
        <el-table-column prop="vendor" label="厂商" width="120" />
        <el-table-column prop="arp_type" label="类型" width="80">
          <template #default="{ row }">
            <el-tag :type="row.arp_type === 'static' ? 'primary' : 'info'" size="small">{{ row.arp_type === 'static' ? '静态' : '动态' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="learned_at" label="学习时间" width="170" sortable>
          <template #default="{ row }">{{ row.learned_at || '-' }}</template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small">{{ statusLabel[row.status] || row.status }}</el-tag>
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
