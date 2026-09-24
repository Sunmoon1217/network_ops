<script setup lang="ts">
import PageLayout from '@/layout/PageLayout.vue'
import { Download, Switch } from '@element-plus/icons-vue'
import DataTable from '@/components/DataTable.vue'
import DataColumn from '@/components/DataColumn.vue'
import { TABLE_KEYS } from '@/constants/tableKeys'
import DataPagination from '@/components/DataPagination.vue'
import FilterBar from '@/components/FilterBar.vue'
import { useCrudApi } from '@/composables/useCrudApi'
import { exportGtmChain, getGtmChain, getGtmChainFacets } from '@/api/config'
import type { GtmChainPool, GtmChainRow, GtmFlatRow, LbTreeRow } from '@/types'

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

/** 去重后顿号连接：二级池行的 order/ratio 显示池内成员的取值集合（逐成员值看三级行） */
const uniqJoin = (vals: (number | null | undefined)[]) =>
  [...new Set(vals.filter((v) => v !== null && v !== undefined))].join('、')

/** 池及其成员 → 池行（成员是池的 children）；找不到上游虚拟服务器的成员标 lost */
const buildPoolTree = (device: number, pool: GtmChainPool): LbTreeRow => ({
  id: `pool-${device}-${pool.name}`,
  kind: 'pool',
  label: pool.name,
  tipLines: [
    `负载算法：${pool.lb_mode || '-'} / 备选：${pool.alternate_mode || '-'}`,
    `回退IP：${pool.fallback_ip || '-'}`,
    `TTL：${pool.ttl ?? '-'}`,
    `健康检查：${pool.monitor?.length ? pool.monitor.join('、') : '-'}`,
  ],
  // 负载算法 = lb_mode / alternate_mode；fallback = 模式 + 回退IP
  mode: [pool.lb_mode, pool.alternate_mode].filter(Boolean).join(' / '),
  fallback: [pool.fallback_mode, pool.fallback_ip ? `（${pool.fallback_ip}）` : ''].filter(Boolean).join(''),
  monitor: pool.monitor?.length ? pool.monitor.join('、') : '',
  order: uniqJoin(pool.members.map((m) => m.order)),
  ratio: uniqJoin(pool.members.map((m) => m.ratio)),
  children: pool.members.map((m, idx) => ({
    id: `member-${device}-${pool.name}-${idx}`,
    kind: 'member' as const,
    // 找到就显示 IP#端口；断链回退显示 server/vserver 名字
    label: m.found && m.address ? addrPort(m.address, m.port) : `${m.server}/${m.vserver}`,
    tipLines: [`${m.server} / ${m.vserver}`, m.found ? '' : '未找到虚拟服务器'].filter(Boolean),
    // 三级行：成员自身的调度权重、成员级健康检查与所属 server 的数据中心
    order: m.order != null ? String(m.order) : '',
    ratio: m.ratio != null ? String(m.ratio) : '',
    monitor: m.monitor || '',
    datacenter: m.datacenter || '',
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

/** 导出扁平宽表为 xlsx（后端 openpyxl 生成、前端只下载 Blob；全量、带当前过滤/搜索） */
const exportLoading = ref(false)
const handleExport = async () => {
  exportLoading.value = true
  try {
    const res = await exportGtmChain({
      device: filterDevice.value || undefined,
      rtype: filterRtype.value || undefined,
      monitor: filterMonitor.value || undefined,
      search: search.value || undefined,
    })
    const url = URL.createObjectURL(res.data as Blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `dn-chains-${new Date().toISOString().slice(0, 10)}.xlsx`
    link.click()
    URL.revokeObjectURL(url)
  } catch {
    ElMessage.error('导出失败')
  } finally {
    exportLoading.value = false
  }
}

/** 视图模式：树形（分级展开）⇄ 扁平（join 宽表，以叶子为行、字段下填），两模式各配各的列 */
const viewMode = ref<'tree' | 'flat'>('tree')
const toggleView = () => (viewMode.value = viewMode.value === 'tree' ? 'flat' : 'tree')

/**
 * 扁平宽表 = SQL join 式展开：**以链最深层为行粒度**——
 * 有成员则每成员一行（wideip + 池字段整条下填），池无成员则以池为行，
 * 无池则以 WideIP 为行；配合专属宽表列（TTL/池监控/成员监控…）融合成一张大表。
 */
const flatRows = computed(() => {
  const out: GtmFlatRow[] = []
  for (const w of rows.value) {
    const wide = { device: w.device_hostname, domain: w.name, rtype: w.rtype || '-', wideAlgo: w.lb_mode || '-' }
    const emptyPool = {
      poolName: '-',
      poolAlgo: '-',
      fallback: '-',
      ttl: '-',
      poolMonitor: '-',
      poolOrder: '-',
      poolRatio: '-',
    }
    const emptyMember = { order: '', ratio: '', memberMonitor: '', datacenter: '' }
    const prefix = `flat-w-${w.device}-${w.name}`
    if (!w.pools.length) {
      out.push({ ...wide, ...emptyPool, ...emptyMember, id: prefix, kind: 'wideip', label: w.name, tipLines: [] })
      continue
    }
    for (const p of w.pools) {
      const pool = {
        poolName: p.name,
        poolAlgo: [p.lb_mode, p.alternate_mode].filter(Boolean).join(' / ') || '-',
        fallback: [p.fallback_mode, p.fallback_ip ? `（${p.fallback_ip}）` : ''].filter(Boolean).join('') || '-',
        ttl: p.ttl != null ? String(p.ttl) : '-',
        poolMonitor: p.monitor?.length ? p.monitor.join('、') : '-',
        // 池级权重 = 池内成员取值集合去重（与树形二级池行同义），成员行也带上下文
        poolOrder: uniqJoin(p.members.map((m: GtmChainPool['members'][number]) => m.order)) || '-',
        poolRatio: uniqJoin(p.members.map((m: GtmChainPool['members'][number]) => m.ratio)) || '-',
      }
      if (!p.members.length) {
        out.push({
          ...wide,
          ...pool,
          ...emptyMember,
          id: `${prefix}-${p.name}-p`,
          kind: 'pool',
          label: p.name,
          tipLines: [`链路：${w.name}（池无成员，以池为行）`],
        })
        continue
      }
      p.members.forEach((m: GtmChainPool['members'][number], idx: number) =>
        out.push({
          ...wide,
          ...pool,
          ...emptyMember,
          id: `${prefix}-${p.name}-m${idx}`,
          kind: 'member',
          // 找到就显示 IP#端口；断链回退显示 server/vserver 名字
          label: m.found && m.address ? addrPort(m.address, m.port) : `${m.server}/${m.vserver}`,
          tipLines: [`${m.server} / ${m.vserver}`, `链路：${w.name} → ${p.name}`, m.found ? '' : '未找到虚拟服务器'].filter(
            Boolean,
          ),
          order: m.order != null ? String(m.order) : '',
          ratio: m.ratio != null ? String(m.ratio) : '',
          memberMonitor: m.monitor || '',
          datacenter: m.datacenter || '',
          state: m.found ? (m.status === 'disabled' ? 'disabled' : 'ok') : 'lost',
        }),
      )
    }
  }
  return out
})

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
      <el-button
        v-if="viewMode === 'flat'"
        type="success"
        plain
        size="small"
        :loading="exportLoading"
        @click="handleExport"
      >
        <el-icon v-if="!exportLoading"><Download /></el-icon>
        导出
      </el-button>
      <el-button type="primary" plain size="small" @click="toggleView">
        <el-icon><Switch /></el-icon>
        切换{{ viewMode === 'tree' ? '扁平' : '树形' }}视图
      </el-button>
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
      <!-- 树形参数经 attrs 透传落到内层 el-table（组件注释里的既定机制）：row-key 必填，箭头/缩进自动加在第一列；
           扁平行没有 children（join 展开行），el-table 视其为叶子即自然平铺 -->
      <DataTable
        :table-key="TABLE_KEYS.gslbWideips"
        :data="viewMode === 'tree' ? treeRows : flatRows"
        :loading="loading"
        row-key="id"
        :tree-props="{ children: 'children' }"
        default-expand-all
        size="small"
      >
        <!-- 树形列组：分级展示，主显示域名/池名/成员地址，name 字段收进 hover -->
        <template v-if="viewMode === 'tree'">
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
          <!-- 一级显示自身 lb_mode，二级显示 池 lb_mode / alternate_mode -->
          <DataColumn prop="mode" label="负载算法" min-width="150" />
          <DataColumn prop="fallback" label="fallback" min-width="160" />
          <DataColumn prop="monitor" label="监控" min-width="130" />
          <DataColumn prop="order" label="Order" min-width="90" />
          <DataColumn prop="ratio" label="Ratio" min-width="90" />
          <DataColumn prop="datacenter" label="数据中心" min-width="110" />
          <DataColumn label="状态" column-key="state" min-width="90">
            <template #default="{ row }">
              <el-tag v-if="row.state === 'ok'" type="success" size="small">正常</el-tag>
              <el-tag v-else-if="row.state === 'disabled'" type="info" size="small">停用</el-tag>
              <el-tag v-else-if="row.state === 'lost'" type="warning" size="small">未找到</el-tag>
              <span v-else class="muted">-</span>
            </template>
          </DataColumn>
        </template>
        <!-- 扁平宽表列组：以叶子为行、wideip/池字段整条下填；TTL/池监控/成员监控一并上列 -->
        <template v-else>
          <DataColumn label="名称" column-key="label" min-width="200">
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
          <DataColumn prop="device" label="设备" min-width="120" />
          <DataColumn prop="domain" label="域名" min-width="170" show-overflow-tooltip />
          <DataColumn prop="rtype" label="记录类型" min-width="85" />
          <DataColumn prop="wideAlgo" label="WideIP算法" min-width="110" />
          <DataColumn prop="poolName" label="池名" min-width="130" />
          <DataColumn prop="poolAlgo" label="池算法" min-width="150" />
          <DataColumn prop="fallback" label="fallback" min-width="160" />
          <DataColumn prop="ttl" label="TTL" min-width="70" />
          <DataColumn prop="poolMonitor" label="池监控" min-width="130" />
          <DataColumn prop="poolOrder" label="池Order" min-width="95" />
          <DataColumn prop="poolRatio" label="池Ratio" min-width="95" />
          <DataColumn prop="order" label="成员Order" min-width="95" />
          <DataColumn prop="ratio" label="成员Ratio" min-width="95" />
          <DataColumn prop="memberMonitor" label="成员监控" min-width="110" />
          <DataColumn prop="datacenter" label="数据中心" min-width="105" />
          <DataColumn label="状态" column-key="state" min-width="85">
            <template #default="{ row }">
              <el-tag v-if="row.state === 'ok'" type="success" size="small">正常</el-tag>
              <el-tag v-else-if="row.state === 'disabled'" type="info" size="small">停用</el-tag>
              <el-tag v-else-if="row.state === 'lost'" type="warning" size="small">未找到</el-tag>
              <span v-else class="muted">-</span>
            </template>
          </DataColumn>
        </template>
      </DataTable>
    </div>
    <DataPagination v-model:page="page" v-model:page-size="pageSize" :total="total" @change="refetch" />
  </PageLayout>
</template>

<style scoped>
.table-wrapper { flex: 1; min-height: 0; background: #fff; border-radius: 8px; overflow: hidden; }
.muted { color: #c0c4cc; }
</style>
