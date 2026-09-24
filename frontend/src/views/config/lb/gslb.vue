<script setup lang="ts">
import PageLayout from '@/layout/PageLayout.vue'
import DataTable from '@/components/DataTable.vue'
import DataColumn from '@/components/DataColumn.vue'
import { TABLE_KEYS } from '@/constants/tableKeys'
import DataPagination from '@/components/DataPagination.vue'
import FilterBar from '@/components/FilterBar.vue'
import { useCrudApi } from '@/composables/useCrudApi'
import { getGtmChain, getGtmChainFacets } from '@/api/config'
import type { GtmChainPool, GtmChainRow, LbTreeRow } from '@/types'

const filterDevice = ref<number | ''>('')
// 两个下拉过滤：WideIP 记录类型（?rtype=）与健康检查类型（?monitor=）
const filterRtype = ref('')
const filterMonitor = ref('')
const rtypeOptions = ref<string[]>([])
const monitorOptions = ref<string[]>([])

// 关联链聚合（/api/lb-chain/gslb/）：每行一条 域名 → 池 → 虚拟服务器，前端再转成树形分级展示
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
  fetchData(() =>
    getGtmChain(
      pageParams({
        device: filterDevice.value || undefined,
        rtype: filterRtype.value || undefined,
        monitor: filterMonitor.value || undefined,
      }),
    ),
  )

/** 下拉选项走 facets；拿不到不阻塞列表（下拉退化为空、可手动清空） */
const loadFacets = async () => {
  try {
    const res = await getGtmChainFacets()
    rtypeOptions.value = res.data?.rtypes ?? []
    monitorOptions.value = res.data?.monitors ?? []
  } catch {
    rtypeOptions.value = []
    monitorOptions.value = []
  }
}

/** 地址与端口用 # 连接：IPv6 自带冒号，':' 分不开两段（与互联网资产分析同约定） */
const addrPort = (address: string, port: string) => (port ? `${address}#${port}` : address)

const KIND_TAG = { wideip: 'primary', pool: 'success', member: 'info', vs: 'primary' } as const
const KIND_LABEL = { wideip: 'Wide IP', pool: '池', member: '成员', vs: '' } as const
// 插槽 row 是 el-table 的 DefaultRow（any），索引前先收敛成 string，找不到就兜底
const kindTagOf = (kind: string) => KIND_TAG[kind as keyof typeof KIND_TAG] ?? 'info'
const kindLabelOf = (kind: string) => KIND_LABEL[kind as keyof typeof KIND_LABEL] ?? kind

/** 池及其成员 → 池行（成员是池的 children）；找不到上游虚拟服务器的成员标 lost */
const buildPoolTree = (device: number, pool: GtmChainPool): LbTreeRow => ({
  id: `pool-${device}-${pool.name}`,
  kind: 'pool',
  label: pool.name,
  tipLines: [
    `负载模式：${pool.lb_mode || '-'}`,
    `回退IP：${pool.fallback_ip || '-'}`,
    `TTL：${pool.ttl ?? '-'}`,
    `健康检查：${pool.monitor?.length ? pool.monitor.join('、') : '-'}`,
  ],
  mode: pool.lb_mode || '-',
  children: pool.members.map((m, idx) => ({
    id: `member-${device}-${pool.name}-${idx}`,
    kind: 'member' as const,
    // 找到就显示 IP#端口；断链回退显示 server/vserver 名字
    label: m.found && m.address ? addrPort(m.address, m.port) : `${m.server}/${m.vserver}`,
    tipLines: [`${m.server} / ${m.vserver}`, m.found ? '' : '未找到虚拟服务器'].filter(Boolean),
    state: m.found ? (m.status === 'disabled' ? 'disabled' : 'ok') : 'lost',
  })),
})

/** 关联链行 → 树行：WideIP 为根，池是它的 child，成员是池的 child */
const buildTree = (r: GtmChainRow): LbTreeRow => ({
  id: `wideip-${r.device}-${r.name}`,
  kind: 'wideip',
  label: r.name,
  tipLines: [],
  device: r.device_hostname,
  rtype: r.rtype || '-',
  mode: r.lb_mode || '-',
  children: r.pools.map((p) => buildPoolTree(r.device, p)),
})

const treeRows = computed(() => rows.value.map(buildTree))

watch(filterDevice, resetAndFetch)
watch(filterRtype, resetAndFetch)
watch(filterMonitor, resetAndFetch)
onMounted(() => {
  loadRows()
  loadFacets()
})
</script>

<template>
  <PageLayout title="域名解析管理">
    <template #actions>
      <FilterBar
        v-model:device="filterDevice"
        v-model:search="search"
        device-type="gslb"
        search-placeholder="搜索 域名/池/服务器/虚拟服务器/IP:端口/健康检查"
        search-width="260px"
      >
        <el-select v-model="filterRtype" placeholder="记录类型" clearable style="width: 110px">
          <el-option v-for="t in rtypeOptions" :key="t" :label="t" :value="t" />
        </el-select>
        <el-select v-model="filterMonitor" placeholder="健康检查" clearable style="width: 150px">
          <el-option v-for="m in monitorOptions" :key="m" :label="m" :value="m" />
        </el-select>
      </FilterBar>
    </template>
    <div class="table-wrapper">
      <!-- 树形参数经 attrs 透传落到内层 el-table（组件注释里的既定机制）：row-key 必填，箭头/缩进自动加在第一列 -->
      <DataTable
        :table-key="TABLE_KEYS.gslbWideips"
        :data="treeRows"
        :loading="loading"
        row-key="id"
        :tree-props="{ children: 'children' }"
        default-expand-all
        size="small"
      >
        <!-- 名称列 = 树首列：主显示域名/池名/成员地址，name 字段收进 hover -->
        <DataColumn prop="label" label="域名 / 名称" min-width="240">
          <template #default="{ row }">
            <el-tooltip v-if="row.tipLines?.length" placement="top">
              <template #content>
                <div v-for="line in row.tipLines" :key="line">{{ line }}</div>
              </template>
              <span>{{ row.label }}</span>
            </el-tooltip>
            <span v-else>{{ row.label }}</span>
          </template>
        </DataColumn>
        <DataColumn prop="device" label="设备" min-width="130" />
        <DataColumn label="类型" column-key="kind" min-width="100">
          <template #default="{ row }">
            <el-tag :type="kindTagOf(row.kind)" size="small">{{ kindLabelOf(row.kind) }}</el-tag>
          </template>
        </DataColumn>
        <DataColumn prop="rtype" label="记录类型" min-width="90" />
        <DataColumn prop="mode" label="负载模式" min-width="130" />
        <DataColumn label="状态" column-key="state" min-width="90">
          <template #default="{ row }">
            <el-tag v-if="row.state === 'ok'" type="success" size="small">正常</el-tag>
            <el-tag v-else-if="row.state === 'disabled'" type="info" size="small">停用</el-tag>
            <el-tag v-else-if="row.state === 'lost'" type="warning" size="small">未找到</el-tag>
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
.muted { color: #c0c4cc; }
</style>
