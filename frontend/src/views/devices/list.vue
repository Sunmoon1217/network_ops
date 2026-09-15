<script setup lang="ts">
import { h } from 'vue'
import { useRouter } from 'vue-router'
import { getDevices } from '@/api/devices'
import { ElButton } from 'element-plus'
import { FixedDir } from 'element-plus/es/components/table-v2/src/constants'
import ImportDevice from './dialogs/ImportDevice.vue'
import PageLayout from '@/ui/PageLayout.vue'
import { useCrudApi } from '@/composables/useCrudApi'
import { useTableHeight } from '@/composables/useTableHeight'

const router = useRouter()
const { tableRef, tableHeight, tableWidth } = useTableHeight()
const { data: devices, loading, search, filteredData, fetchData } = useCrudApi(['hostname', 'ip_address'])

const importDialogVisible = ref(false)

const goToConfig = (row: any) => router.push(`/devices/${row.id}/config`)
const goToHistory = (row: any) => router.push(`/devices/${row.id}/history`)

const columns = [
  { key: 'hostname', title: '主机名', dataKey: 'hostname', width: 260 },
  { key: 'device_model_name', title: '设备型号', dataKey: 'device_model_name', width: 260 },
  { key: 'device_type_display', title: '类型', dataKey: 'device_type_display', width: 100 },
  { key: 'security_zone_name', title: '区域', dataKey: 'security_zone_name', width: 140 },
  { key: 'ip_address', title: '管理IP', dataKey: 'ip_address', width: 140 },
  { key: 'idc_name', title: '数据中心', dataKey: 'idc_name', width: 140 },
  { key: 'cabinet_name', title: '机柜位置', dataKey: 'cabinet_name', width: 260 },
  { key: 'u_position', title: 'U位', dataKey: 'u_position', width: 60 },
  { key: 'height', title: '高度', dataKey: 'height', width: 60 },
  { key: 'remark', title: '备注', dataKey: 'remark', width: 200 },
  { key: 'operation', title: '操作', width: 200, fixed: FixedDir.RIGHT },
]

onMounted(() => fetchData(getDevices))
</script>

<template>
  <PageLayout title="设备列表">
    <template #actions>
      <el-input v-model="search" placeholder="搜索主机名 / IP" clearable style="width: 220px" />
      <el-button @click="importDialogVisible = true">导入</el-button>
      <el-button type="primary" @click="router.push('/devices/create')">添加设备</el-button>
    </template>
    <div ref="tableRef" class="table-wrapper">
      <el-table-v2
        v-loading="loading"
        :columns="columns"
        :data="filteredData"
        :height="tableHeight"
        :width="tableWidth"
        :fixed="true"
      >
        <template #header-cell="{ column }">
          <span style="font-weight: 600">{{ column.title }}</span>
        </template>
        <template #cell="{ column, rowData }">
          <template v-if="column.key === 'operation'">
            <el-button size="small" link type="primary" @click="goToConfig(rowData)">配置</el-button>
            <el-button size="small" link type="info" @click="goToHistory(rowData)">历史</el-button>
            <el-button size="small" link type="warning" @click="router.push(`/devices/${rowData.id}/edit`)">编辑</el-button>
          </template>
          <template v-else>
            {{ rowData[column.dataKey!] ?? '-' }}
          </template>
        </template>
      </el-table-v2>
    </div>
    <ImportDevice v-model:visible="importDialogVisible" @success="() => fetchData(getDevices)" />
  </PageLayout>
</template>

<style scoped>
.table-wrapper { flex: 1; min-height: 0; }
</style>
