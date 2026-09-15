<script setup lang="ts">
import PageLayout from '@/ui/PageLayout.vue'
import DataTable from '@/ui/DataTable.vue'
import DeviceFilter from '@/ui/DeviceFilter.vue'
import { useCrudApi } from '@/composables/useCrudApi'
import api from '@/api/index'

const { data: accounts, loading, search, filteredData, fetchData } = useCrudApi(['username', 'device_hostname', 'description'])
const filterDevice = ref<number | ''>('')

const displayed = computed(() => {
  if (!filterDevice.value) return filteredData.value
  return filteredData.value.filter((a: any) => a.device === filterDevice.value)
})

const fetchAll = () => {
  const params: Record<string, any> = {}
  if (filterDevice.value) params.device = filterDevice.value
  fetchData(() => api.get('/api/assets/device-accounts/', { params }))
}

const authTypeLabel: Record<string, string> = { password: '密码', 'ssh-key': 'SSH密钥', both: '双因素' }
const authTypeTag: Record<string, string> = { password: '', 'ssh-key': 'success', both: 'warning' }
const privilegeLabel: Record<string, string> = { admin: '管理员', operator: '操作员', readonly: '只读' }
const privilegeTag: Record<string, string> = { admin: 'danger', operator: 'warning', readonly: 'info' }

watch(filterDevice, fetchAll)
onMounted(fetchAll)
</script>

<template>
  <PageLayout title="设备账号">
    <template #actions>
      <DeviceFilter v-model="filterDevice" />
      <el-input v-model="search" placeholder="搜索用户名/设备/描述" clearable style="width: 220px" />
    </template>
    <div class="table-wrapper">
      <DataTable :data="displayed" :loading="loading">
        <el-table-column prop="device_hostname" label="设备" width="150" sortable />
        <el-table-column prop="username" label="用户名" width="140" sortable />
        <el-table-column prop="auth_type" label="认证方式" width="110">
          <template #default="{ row }">
            <el-tag :type="(authTypeTag[row.auth_type] || 'info') as any" size="small">{{ authTypeLabel[row.auth_type] || row.auth_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="privilege" label="权限级别" width="100">
          <template #default="{ row }">
            <el-tag :type="(privilegeTag[row.privilege] || 'info') as any" size="small">{{ privilegeLabel[row.privilege] || row.privilege }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="enabled" label="启用" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? '是' : '否' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="活跃" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '是' : '否' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="180" show-overflow-tooltip />
      </DataTable>
    </div>
  </PageLayout>
</template>

<style scoped>
.table-wrapper { flex: 1; min-height: 0; background: #fff; border-radius: 8px; overflow: hidden; }
</style>
