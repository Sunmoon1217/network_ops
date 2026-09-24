<script setup lang="ts">
import PageLayout from '@/layout/PageLayout.vue'
import DataTable from '@/components/DataTable.vue'
import DataColumn from '@/components/DataColumn.vue'
import { TABLE_KEYS } from '@/constants/tableKeys'
import DataPagination from '@/components/DataPagination.vue'
import FilterBar from '@/components/FilterBar.vue'
import { useCrudApi } from '@/composables/useCrudApi'
import { getGtmChain } from '@/api/config'
import type { GtmChainRow } from '@/types'

const filterDevice = ref<number | ''>('')

// 单表聚合：每行一条 域名 → 池 → 虚拟服务器 关联链（/api/lb-chain/gslb/），
// 原来 Wide IP / Pool 两个 tab 拼不出关联，现在压进一行
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
} = useCrudApi<GtmChainRow>()

const loadRows = () =>
  fetchData(() => getGtmChain(pageParams({ device: filterDevice.value || undefined })))

/** 地址与端口用 # 连接：IPv6 自带冒号，':' 分不开两段（与互联网资产分析同约定） */
const addrPort = (address: string, port: string) => (port ? `${address}#${port}` : address)

/** 成员的 hover 文案：找到就是 server/vserver 名，没找到说明链在这里断了 */
const memberTip = (m: { server: string; vserver: string; found: boolean }) =>
  m.found ? `${m.server} / ${m.vserver}` : `${m.server} / ${m.vserver}（未找到虚拟服务器）`

watch(filterDevice, resetAndFetch)
onMounted(loadRows)
</script>

<template>
  <PageLayout title="域名解析管理">
    <template #actions>
      <FilterBar
        v-model:device="filterDevice"
        v-model:search="search"
        device-type="gslb"
        search-placeholder="搜索域名/池/设备"
        search-width="220px"
      />
    </template>
    <div class="table-wrapper">
      <DataTable :table-key="TABLE_KEYS.gslbWideips" :data="rows" :loading="loading" size="small">
        <DataColumn prop="device_hostname" label="设备" width="130" sortable />
        <!-- 主显示是域名本身 -->
        <DataColumn prop="name" label="域名" min-width="210" sortable show-overflow-tooltip />
        <DataColumn prop="rtype" label="记录类型" min-width="90" />
        <DataColumn prop="lb_mode" label="负载模式" min-width="110" />
        <!-- 解析链：池名（hover 出池参数）→ 成员 IP#端口（hover 出 server/vserver 名） -->
        <DataColumn label="解析链" column-key="chain" min-width="380">
          <template #default="{ row }">
            <div v-if="row.pools?.length" class="chain">
              <div v-for="p in row.pools" :key="p.name" class="chain-seg">
                <el-tooltip placement="top">
                  <template #content>
                    <div>{{ p.name }}</div>
                    <div>负载模式：{{ p.lb_mode || '-' }}</div>
                    <div>回退IP：{{ p.fallback_ip || '-' }}</div>
                    <div>TTL：{{ p.ttl ?? '-' }}</div>
                  </template>
                  <span class="name-hot">{{ p.name }}</span>
                </el-tooltip>
                <span class="arrow">→</span>
                <template v-if="p.members?.length">
                  <el-tooltip
                    v-for="(m, idx) in p.members"
                    :key="idx"
                    :content="memberTip(m)"
                    placement="top"
                  >
                    <el-tag size="small" :type="m.found ? 'success' : 'warning'">
                      {{ m.found && m.address ? addrPort(m.address, m.port) : `${m.server}/${m.vserver}` }}
                    </el-tag>
                  </el-tooltip>
                </template>
                <span v-else class="muted">无成员</span>
              </div>
            </div>
            <span v-else class="muted">未关联池</span>
          </template>
        </DataColumn>
      </DataTable>
    </div>
    <DataPagination v-model:page="page" v-model:page-size="pageSize" :total="total" @change="refetch" />
  </PageLayout>
</template>

<style scoped>
.table-wrapper { flex: 1; min-height: 0; background: #fff; border-radius: 8px; overflow: hidden; }
.chain { display: flex; flex-direction: column; gap: 4px; }
.chain-seg { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.arrow { color: #c0c4cc; }
.name-hot { font-weight: 500; }
.muted { color: #c0c4cc; }
</style>
