<script setup lang="ts">
import PageLayout from '@/layout/PageLayout.vue'
import DataTable from '@/components/DataTable.vue'
import DataColumn from '@/components/DataColumn.vue'
import { TABLE_KEYS } from '@/constants/tableKeys'
import DataPagination from '@/components/DataPagination.vue'
import FilterBar from '@/components/FilterBar.vue'
import { useCrudApi } from '@/composables/useCrudApi'
import { getLtmChain } from '@/api/config'
import type { LtmChainRow } from '@/types'

const filterDevice = ref<number | ''>('')

// 单表聚合：每行一条 VS → 池 → 成员 关联链（/api/lb-chain/slb/ 按页拼好整链），
// 原来 VS / Pool 两个 tab 各看各的、拼不出关联，现在压进一行
const {
  data: rows,
  loading,
  page,
  pageSize,
  total,
  fetchData,
  refetch,
  pageParams,
  resetAndFetch,
  search,
} = useCrudApi<LtmChainRow>()

const loadRows = () =>
  fetchData(() => getLtmChain(pageParams({ device: filterDevice.value || undefined })))

/** 地址与端口用 # 连接：IPv6 自带冒号，':' 分不开两段（与互联网资产分析同约定） */
const addrPort = (address: string, port: string) => (port ? `${address}#${port}` : address)

watch(filterDevice, resetAndFetch)
onMounted(loadRows)
</script>

<template>
  <PageLayout title="负载均衡管理">
    <template #actions>
      <FilterBar
        v-model:device="filterDevice"
        v-model:search="search"
        device-type="slb"
        search-placeholder="搜索名称/地址/池/设备"
        search-width="220px"
      />
    </template>
    <div class="table-wrapper">
      <DataTable :table-key="TABLE_KEYS.slbVirtualServers" :data="rows" :loading="loading" size="small">
        <DataColumn prop="device_hostname" label="设备" width="130" sortable />
        <!-- 主显示是 IP:端口，VS 的 name 收进 hover -->
        <DataColumn prop="vs_address" label="虚拟地址" min-width="170">
          <template #default="{ row }">
            <el-tooltip :content="row.name" placement="top">
              <span>{{ addrPort(row.vs_address, row.vs_port) }}</span>
            </el-tooltip>
          </template>
        </DataColumn>
        <DataColumn prop="protocol" label="协议" min-width="80" />
        <!-- 关联池：池只有名字可显示，负载模式 / 监控放 hover -->
        <DataColumn label="关联池" column-key="pool" min-width="170">
          <template #default="{ row }">
            <el-tooltip v-if="row.pool" placement="top">
              <template #content>
                <div>{{ row.pool.name }}</div>
                <div>负载模式：{{ row.pool.mode || '-' }}</div>
                <div>监控：{{ row.pool.monitors?.length ? row.pool.monitors.join('、') : '-' }}</div>
              </template>
              <span class="name-hot">{{ row.pool.name }}</span>
            </el-tooltip>
            <span v-else class="muted">未关联池</span>
          </template>
        </DataColumn>
        <!-- 成员显示 地址#端口，成员 name 收进 hover -->
        <DataColumn label="池成员" column-key="members" min-width="300">
          <template #default="{ row }">
            <div v-if="row.members?.length" class="chips">
              <el-tooltip
                v-for="m in row.members"
                :key="`${m.name}:${m.port}`"
                :content="m.name"
                placement="top"
              >
                <el-tag size="small" type="info">
                  {{ m.address ? addrPort(m.address, m.port) : m.name }}
                </el-tag>
              </el-tooltip>
            </div>
            <span v-else class="muted">-</span>
          </template>
        </DataColumn>
        <DataColumn prop="snat_type" label="SNAT" min-width="110">
          <template #default="{ row }">
            <span v-if="row.snat_type">{{ row.snat_type }}</span>
            <span v-else class="muted">-</span>
          </template>
        </DataColumn>
        <DataColumn prop="persist" label="会话保持" min-width="110">
          <template #default="{ row }">
            <span v-if="row.persist">{{ row.persist }}</span>
            <span v-else class="muted">-</span>
          </template>
        </DataColumn>
      </DataTable>
    </div>
    <DataPagination v-model:page="page" v-model:page-size="pageSize" :total="total" @change="refetch" />
  </PageLayout>
</template>

<style scoped>
.table-wrapper { flex: 1; min-height: 0; background: #fff; border-radius: 8px; overflow: hidden; }
.chips { display: flex; flex-wrap: wrap; gap: 4px; }
.name-hot { font-weight: 500; }
.muted { color: #c0c4cc; }
</style>
