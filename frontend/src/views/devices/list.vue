<script setup lang="ts">
import { useRouter } from 'vue-router'
import { getDevices } from '@/api/devices'
import ImportDevice from './dialogs/ImportDevice.vue'
import PageLayout from '@/layout/PageLayout.vue'
import DataTable from '@/components/DataTable.vue'
import DataColumn from '@/components/DataColumn.vue'
import DataPagination from '@/components/DataPagination.vue'
import { useCrudApi } from '@/composables/useCrudApi'
import { TABLE_KEYS } from '@/constants/tableKeys'

const router = useRouter()

const { data: devices, loading, search, page, pageSize, total, fetchData, refetch, pageParams } = useCrudApi()

const importDialogVisible = ref(false)

const goToConfig = (row: any) => router.push(`/devices/${row.id}/config`)
const goToHistory = (row: any) => router.push(`/devices/${row.id}/history`)

const fetchAll = () => fetchData(() => getDevices(pageParams()))

onMounted(fetchAll)
</script>

<template>
  <PageLayout title="设备列表">
    <template #actions>
      <el-input v-model="search" placeholder="搜索主机名 / IP" clearable style="width: 220px" />
      <el-button @click="importDialogVisible = true">导入</el-button>
      <el-button type="primary" @click="router.push('/devices/create')">添加设备</el-button>
    </template>
    <div class="table-wrapper">
      <DataTable :table-key="TABLE_KEYS.deviceList" :data="devices" :loading="loading">
        <DataColumn prop="hostname" label="主机名" :width="260" show-overflow-tooltip />
        <DataColumn
          prop="device_model_name"
          label="设备型号"
          :width="260"
          show-overflow-tooltip
        />
        <DataColumn prop="device_type_display" label="类型" :width="100" />
        <DataColumn prop="security_zone_name" label="区域" :width="140" />
        <DataColumn prop="ip_address" label="管理IP" :width="140" />
        <DataColumn prop="idc_name" label="数据中心" :width="140" />
        <DataColumn prop="cabinet_name" label="机柜位置" :width="260" show-overflow-tooltip />
        <DataColumn prop="u_position" label="U位" :width="60" align="center" />
        <DataColumn prop="height" label="高度" :width="60" align="center" />
        <DataColumn prop="remark" label="备注" :width="200" show-overflow-tooltip />
        <DataColumn column-key="operation" label="操作" :width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="goToConfig(row)">配置</el-button>
            <el-button size="small" link type="info" @click="goToHistory(row)">历史</el-button>
            <el-button size="small" link type="warning" @click="router.push(`/devices/${row.id}/edit`)">编辑</el-button>
          </template>
        </DataColumn>
      </DataTable>
    </div>
    <DataPagination v-model:page="page" v-model:page-size="pageSize" :total="total" @change="refetch" />
    <ImportDevice v-model:visible="importDialogVisible" @success="fetchAll" />
  </PageLayout>
</template>

<style scoped>
.table-wrapper { flex: 1; min-height: 0; background: #fff; border-radius: 8px; overflow: hidden; }
</style>
