<script setup lang="ts">
import PageLayout from '@/layout/PageLayout.vue'
import DataTable from '@/components/DataTable.vue'
import DataPagination from '@/components/DataPagination.vue'
import {
  getSnmpConfigs, deleteSnmpConfig,
  getNtpConfigs, deleteNtpConfig,
  getSyslogConfigs, deleteSyslogConfig,
  updateSnmpConfig, updateNtpConfig, updateSyslogConfig,
} from '@/api/baseline'
import { useCrudApi } from '@/composables/useCrudApi'

const router = useRouter()
const activeTab = ref('snmp')

// 三个 tab 各自持有独立的分页与加载状态
const {
  data: snmpList, loading: snmpLoading, page: snmpPage, pageSize: snmpPageSize,
  total: snmpTotal, fetchData: fetchSnmpData, refetch: refetchSnmp, pageParams: snmpPageParams,
  handleDelete: deleteSnmpRow,
} = useCrudApi()
const {
  data: ntpList, loading: ntpLoading, page: ntpPage, pageSize: ntpPageSize,
  total: ntpTotal, fetchData: fetchNtpData, refetch: refetchNtp, pageParams: ntpPageParams,
  handleDelete: deleteNtpRow,
} = useCrudApi()
const {
  data: syslogList, loading: syslogLoading, page: syslogPage, pageSize: syslogPageSize,
  total: syslogTotal, fetchData: fetchSyslogData, refetch: refetchSyslog, pageParams: syslogPageParams,
  handleDelete: deleteSyslogRow,
} = useCrudApi()

// 各 tab 的加载器：fetcher 内用各自的 pageParams 拼装分页参数
const loaders = {
  snmp: () => fetchSnmpData(() => getSnmpConfigs(snmpPageParams())),
  ntp: () => fetchNtpData(() => getNtpConfigs(ntpPageParams())),
  syslog: () => fetchSyslogData(() => getSyslogConfigs(syslogPageParams())),
}

// tab 首次进入时才拉取，之后切换复用已有数据（翻页由 refetch 负责）
const loadedTabs = ref<Record<string, boolean>>({ snmp: false, ntp: false, syslog: false })

const loadTab = async (tab: string) => {
  if (loadedTabs.value[tab]) return
  loadedTabs.value[tab] = true
  await loaders[tab as keyof typeof loaders]()
}

watch(activeTab, tab => { loadTab(tab) })
onMounted(() => { loadTab(activeTab.value) })
</script>

<template>
  <PageLayout title="基线管理">
    <el-tabs v-model="activeTab" class="page-tabs">
      <el-tab-pane label="SNMP" name="snmp">
        <div class="tab-toolbar">
          <el-button type="primary" size="small" @click="router.push('/devices/baseline/snmp/create')">新增</el-button>
        </div>
        <DataTable :data="snmpList" :loading="snmpLoading" size="small" height="">
          <el-table-column prop="device_hostname" label="设备" width="150" />
          <el-table-column prop="version" label="版本" width="80" />
          <el-table-column prop="community_read" label="读社区" width="120" show-overflow-tooltip />
          <el-table-column prop="community_write" label="写社区" width="120" show-overflow-tooltip />
          <el-table-column prop="port" label="端口" width="80" />
          <el-table-column prop="trap_enabled" label="Trap" width="70" align="center">
            <template #default="{ row }">
              <el-tag :type="row.trap_enabled ? 'success' : 'info'" size="small">{{ row.trap_enabled ? '开' : '关' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="enabled" label="启用" width="70" align="center">
            <template #default="{ row }">
              <el-switch v-model="row.enabled" size="small" @change="updateSnmpConfig(row.id, { enabled: row.enabled })" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right" align="center">
            <template #default="{ row }">
              <el-button size="small" link type="primary" @click="router.push(`/devices/baseline/snmp/${row.id}/edit`)">编辑</el-button>
              <el-button size="small" link type="danger" @click="deleteSnmpRow('SNMP配置', () => deleteSnmpConfig(row.id), refetchSnmp)">删除</el-button>
            </template>
          </el-table-column>
        </DataTable>
        <DataPagination v-model:page="snmpPage" v-model:page-size="snmpPageSize" :total="snmpTotal" @change="refetchSnmp" />
      </el-tab-pane>

      <el-tab-pane label="NTP" name="ntp">
        <div class="tab-toolbar">
          <el-button type="primary" size="small" @click="router.push('/devices/baseline/ntp/create')">新增</el-button>
        </div>
        <DataTable :data="ntpList" :loading="ntpLoading" size="small" height="">
          <el-table-column prop="device_hostname" label="设备" width="150" />
          <el-table-column prop="server1" label="NTP服务器1" width="150" />
          <el-table-column prop="server2" label="NTP服务器2" width="150" />
          <el-table-column prop="server3" label="NTP服务器3" width="150" />
          <el-table-column prop="timezone" label="时区" width="100" />
          <el-table-column prop="sync_interval" label="同步间隔" width="90" />
          <el-table-column prop="enabled" label="启用" width="70" align="center">
            <template #default="{ row }">
              <el-switch v-model="row.enabled" size="small" @change="updateNtpConfig(row.id, { enabled: row.enabled })" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right" align="center">
            <template #default="{ row }">
              <el-button size="small" link type="primary" @click="router.push(`/devices/baseline/ntp/${row.id}/edit`)">编辑</el-button>
              <el-button size="small" link type="danger" @click="deleteNtpRow('NTP配置', () => deleteNtpConfig(row.id), refetchNtp)">删除</el-button>
            </template>
          </el-table-column>
        </DataTable>
        <DataPagination v-model:page="ntpPage" v-model:page-size="ntpPageSize" :total="ntpTotal" @change="refetchNtp" />
      </el-tab-pane>

      <el-tab-pane label="Syslog" name="syslog">
        <div class="tab-toolbar">
          <el-button type="primary" size="small" @click="router.push('/devices/baseline/syslog/create')">新增</el-button>
        </div>
        <DataTable :data="syslogList" :loading="syslogLoading" size="small" height="">
          <el-table-column prop="device_hostname" label="设备" width="150" />
          <el-table-column prop="server1" label="日志服务器1" width="150" />
          <el-table-column prop="server2" label="日志服务器2" width="150" />
          <el-table-column prop="port" label="端口" width="80" />
          <el-table-column prop="facility" label="Facility" width="100" />
          <el-table-column prop="level" label="日志级别" width="120" />
          <el-table-column prop="enabled" label="启用" width="70" align="center">
            <template #default="{ row }">
              <el-switch v-model="row.enabled" size="small" @change="updateSyslogConfig(row.id, { enabled: row.enabled })" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right" align="center">
            <template #default="{ row }">
              <el-button size="small" link type="primary" @click="router.push(`/devices/baseline/syslog/${row.id}/edit`)">编辑</el-button>
              <el-button size="small" link type="danger" @click="deleteSyslogRow('Syslog配置', () => deleteSyslogConfig(row.id), refetchSyslog)">删除</el-button>
            </template>
          </el-table-column>
        </DataTable>
        <DataPagination v-model:page="syslogPage" v-model:page-size="syslogPageSize" :total="syslogTotal" @change="refetchSyslog" />
      </el-tab-pane>
    </el-tabs>
  </PageLayout>
</template>

<style scoped>
.page-tabs { flex: 1; min-height: 0; }
.tab-toolbar { margin-bottom: 12px; }
</style>
