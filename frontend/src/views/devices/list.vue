<script setup lang="ts">
import { useRouter } from 'vue-router'
import { getDevices } from '@/api/devices'
import ImportDevice from './dialogs/ImportDevice.vue'
import PageLayout from '@/layout/PageLayout.vue'
import DataTable from '@/components/DataTable.vue'
import DataPagination from '@/components/DataPagination.vue'
import { useCrudApi } from '@/composables/useCrudApi'
import { useTablePrefs } from '@/composables/useTablePrefs'
import { TABLE_KEYS } from '@/constants/tableKeys'

const router = useRouter()
const { widthFor, onHeaderDragend } = useTablePrefs(TABLE_KEYS.deviceList)

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
      <DataTable :data="devices" :loading="loading" @header-dragend="onHeaderDragend">
        <el-table-column prop="hostname" label="主机名" :width="widthFor('hostname', 260)" show-overflow-tooltip />
        <el-table-column
          prop="device_model_name"
          label="设备型号"
          :width="widthFor('device_model_name', 260)"
          show-overflow-tooltip
        />
        <el-table-column prop="device_type_display" label="类型" :width="widthFor('device_type_display', 100)" />
        <el-table-column prop="security_zone_name" label="区域" :width="widthFor('security_zone_name', 140)" />
        <el-table-column prop="ip_address" label="管理IP" :width="widthFor('ip_address', 140)" />
        <el-table-column prop="idc_name" label="数据中心" :width="widthFor('idc_name', 140)" />
        <el-table-column prop="cabinet_name" label="机柜位置" :width="widthFor('cabinet_name', 260)" show-overflow-tooltip />
        <el-table-column prop="u_position" label="U位" :width="widthFor('u_position', 60)" align="center" />
        <el-table-column prop="height" label="高度" :width="widthFor('height', 60)" align="center" />
        <el-table-column prop="remark" label="备注" :width="widthFor('remark', 200)" show-overflow-tooltip />
        <el-table-column column-key="operation" label="操作" :width="widthFor('operation', 200)" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="goToConfig(row)">配置</el-button>
            <el-button size="small" link type="info" @click="goToHistory(row)">历史</el-button>
            <el-button size="small" link type="warning" @click="router.push(`/devices/${row.id}/edit`)">编辑</el-button>
          </template>
        </el-table-column>
      </DataTable>
    </div>
    <DataPagination v-model:page="page" v-model:page-size="pageSize" :total="total" @change="refetch" />
    <ImportDevice v-model:visible="importDialogVisible" @success="fetchAll" />
  </PageLayout>
</template>

<style scoped>
.table-wrapper { flex: 1; min-height: 0; background: #fff; border-radius: 8px; overflow: hidden; }
</style>
