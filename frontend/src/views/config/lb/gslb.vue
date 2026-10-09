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
import type { GtmChainPool, GtmChainRow, GtmFlatRow, LbPanelRow, LbRootRow } from '@/types'

const filterDevice = ref<number | ''>('')
// 两个下拉过滤：WideIP 记录类型（?rtype=）与健康检查类型（?monitor=）
const filterRtype = ref('')
const filterMonitor = ref('')
const rtypeOptions = ref<string[]>([])
const monitorOptions = ref<string[]>([])

// 关联链聚合（/api/lb-chain/gslb/）：每行一条 域名 → 池 → 虚拟服务器，
// 前端转成「根行（WideIP 自身字段）+ 展开面板（池 → 成员）」——两者各用各的列
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
// 成员链路状态 → 标签色与文案（记录式明细里的「状态」字段用）
const STATE_TAG = { ok: 'success', disabled: 'info', lost: 'warning' } as const
const STATE_LABEL = { ok: '正常', disabled: '停用', lost: '未找到' } as const
const stateTagOf = (state: string) => STATE_TAG[state as keyof typeof STATE_TAG] ?? 'info'
const stateLabelOf = (state: string) => STATE_LABEL[state as keyof typeof STATE_LABEL] ?? state

/** 去重后顿号连接：面板池行的 order/ratio 显示池内成员的取值集合（逐成员值看成员行） */
const uniqJoin = (vals: (number | null | undefined)[]) =>
  [...new Set(vals.filter((v) => v !== null && v !== undefined))].join('、')

/** 池及其成员 → 面板池行（成员是池的 children）；找不到上游虚拟服务器的成员标 lost */
const buildPoolPanel = (device: number, pool: GtmChainPool): LbPanelRow => ({
  id: `pool-${device}-${pool.name}`,
  kind: 'pool',
  label: pool.name,
  tipLines: [],
  // 负载算法 = lb_mode / alternate_mode；fallback = 模式 + 回退IP
  algo: [pool.lb_mode, pool.alternate_mode].filter(Boolean).join(' / '),
  fallback: [pool.fallback_mode, pool.fallback_ip ? `（${pool.fallback_ip}）` : ''].filter(Boolean).join(''),
  ttl: pool.ttl != null ? String(pool.ttl) : '',
  monitor: pool.monitor?.length ? pool.monitor.join('、') : '',
  order: uniqJoin(pool.members.map((m) => m.order)),
  ratio: uniqJoin(pool.members.map((m) => m.ratio)),
  children: pool.members.map((m, idx) => ({
    id: `member-${device}-${pool.name}-${idx}`,
    kind: 'member' as const,
    // 找到就显示 IP#端口；断链回退显示 server/vserver 名字
    label: m.found && m.address ? addrPort(m.address, m.port) : `${m.server}/${m.vserver}`,
    tipLines: [`${m.server} / ${m.vserver}`, m.found ? '' : '未找到虚拟服务器'].filter(Boolean),
    // 成员行：成员自身的调度权重、成员级健康检查与所属 server 的数据中心
    order: m.order != null ? String(m.order) : '',
    ratio: m.ratio != null ? String(m.ratio) : '',
    monitor: m.monitor || '',
    datacenter: m.datacenter || '',
    state: m.found ? (m.status === 'disabled' ? 'disabled' : 'ok') : 'lost',
  })),
})

/** 关联链行 → 根行：WideIP 上主表，池/成员收进 panel 由展开列渲染 */
const buildRoot = (r: GtmChainRow): LbRootRow => ({
  id: `wideip-${r.device}-${r.name}`,
  kind: 'wideip',
  label: r.name,
  tipLines: [],
  device: r.device_hostname,
  rtype: r.rtype || '-',
  mode: r.lb_mode || '-',
  panel: r.pools.map((p) => buildPoolPanel(r.device, p)),
})

const rootRows = computed(() => rows.value.map(buildRoot))

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

/**
 * 视图模式：明细（根行 + 展开面板，池/成员收在面板里）⇄ 扁平（join 宽表，以叶子为行、
 * 字段下填），两模式各配各的列。
 */
const viewMode = ref<'detail' | 'flat'>('detail')
const toggleView = () => (viewMode.value = viewMode.value === 'detail' ? 'flat' : 'detail')

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
        // 池级权重 = 池内成员取值集合去重（与展开面板的池行同义），成员行也带上下文
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
        :loading="exportLoading"
        @click="handleExport"
      >
        <el-icon v-if="!exportLoading"><Download /></el-icon>
        导出
      </el-button>
      <el-button type="primary" plain @click="toggleView">
        <el-icon><Switch /></el-icon>
        切换{{ viewMode === 'detail' ? '扁平' : '明细' }}视图
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
      <!-- 展开列经 attrs 透传落到内层 el-table（组件注释里的既定机制）：row-key 必填；
           扁平视图没有展开列，主表只有一层叶子行 -->
      <DataTable
        :table-key="TABLE_KEYS.gslbWideips"
        :data="viewMode === 'detail' ? rootRows : flatRows"
        :loading="loading"
        row-key="id"
        size="small"
      >
        <!-- 明细列组：主表只放 WideIP 自身的字段；池 / 成员的字段全在展开面板里，与这些列完全无关 -->
        <template v-if="viewMode === 'detail'">
          <!-- 展开列：单元格只画箭头，面板内容跨整行渲染，不参与列宽/顺序/显隐偏好 -->
          <DataColumn type="expand" label="">
            <template #default="{ row }">
              <!-- 面板整体右移一个展开列宽（48px，与 DataColumn type=expand 的列宽同源）：
                   子表首列对齐主表第一列（名称），而不是箭头列 -->
              <div class="panel">
                <div v-if="!row.panel?.length" class="panel-empty">无关联池</div>
                <!-- 记录式明细（不要表头）：一行一条记录，字段「标签：值」平铺；
                     上下双线（===）、记录之间单线（---） -->
                <div v-else class="panel-records">
                  <template v-for="p in row.panel" :key="p.id">
                    <div class="record">
                      <span class="field"><span class="k">池：</span>{{ p.label }}</span>
                      <span v-if="p.algo" class="field"><span class="k">负载算法：</span>{{ p.algo }}</span>
                      <span v-if="p.fallback" class="field"><span class="k">fallback：</span>{{ p.fallback }}</span>
                      <span v-if="p.ttl" class="field"><span class="k">TTL：</span>{{ p.ttl }}</span>
                      <span v-if="p.monitor" class="field"><span class="k">监控：</span>{{ p.monitor }}</span>
                      <span v-if="p.order" class="field"><span class="k">Order：</span>{{ p.order }}</span>
                      <span v-if="p.ratio" class="field"><span class="k">Ratio：</span>{{ p.ratio }}</span>
                    </div>
                    <div v-for="m in p.children" :key="m.id" class="record">
                      <span class="field"><span class="k">名称：</span>{{ m.tipLines[0] || m.label }}</span>
                      <span v-if="m.tipLines[0] && m.label !== m.tipLines[0]" class="field">
                        <span class="k">地址：</span>{{ m.label }}
                      </span>
                      <span v-if="m.order" class="field"><span class="k">Order：</span>{{ m.order }}</span>
                      <span v-if="m.ratio" class="field"><span class="k">Ratio：</span>{{ m.ratio }}</span>
                      <span v-if="m.monitor" class="field"><span class="k">监控：</span>{{ m.monitor }}</span>
                      <span v-if="m.datacenter" class="field"><span class="k">数据中心：</span>{{ m.datacenter }}</span>
                      <span v-if="m.state" class="field">
                        <span class="k">状态：</span>
                        <el-tag :type="stateTagOf(m.state)" size="small">{{ stateLabelOf(m.state) }}</el-tag>
                      </span>
                    </div>
                  </template>
                </div>
              </div>
            </template>
          </DataColumn>
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
          <!-- 只有 WideIP 自身的 lb_mode 上主表；池的算法/fallback/TTL/权重等一律进面板 -->
          <DataColumn prop="mode" label="负载算法" min-width="150" />
        </template>
        <!-- 扁平宽表列组：按链层级排序——wideip 段 → 池段（权重/名/监控）→ 成员段 -->
        <template v-else>
          <DataColumn prop="device" label="设备" min-width="120" />
          <DataColumn prop="domain" label="域名" min-width="170" show-overflow-tooltip />
          <DataColumn prop="rtype" label="记录类型" min-width="85" />
          <DataColumn prop="wideAlgo" label="WideIP算法" min-width="110" />
          <DataColumn prop="poolOrder" label="池Order" min-width="95" />
          <DataColumn prop="poolRatio" label="池Ratio" min-width="95" />
          <DataColumn prop="poolName" label="池名" min-width="130" />
          <DataColumn prop="poolMonitor" label="池监控" min-width="130" />
          <DataColumn prop="poolAlgo" label="池算法" min-width="150" />
          <DataColumn prop="fallback" label="fallback" min-width="160" />
          <DataColumn prop="ttl" label="TTL" min-width="70" />
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
.table-wrapper { flex: 1; min-height: 0; background: var(--el-bg-color); border-radius: 8px; overflow: hidden; }
.muted { color: var(--el-text-color-placeholder); }
/* 展开面板：右移一个展开列宽（48px），子表首列与主表首列（名称）对齐 */
.panel { padding-left: 48px; }
/* 记录式明细：上下双线（===）、记录间单线（---），字段平铺、放不下自动换行 */
.panel-records {
  border-top: 3px double var(--el-border-color);
  border-bottom: 3px double var(--el-border-color);
  padding: 2px 0;
}
.record {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 24px;
  padding: 6px 2px;
}
.record + .record { border-top: 1px solid var(--el-border-color-lighter); }
/* 首字段（池名 / 成员名）加重，作为这条记录的锚点 */
.record > .field:first-child { font-weight: 600; color: var(--el-text-color-primary); }
.field { font-size: 13px; color: var(--el-text-color-regular); white-space: nowrap; }
.field .k { color: var(--el-text-color-secondary); font-weight: 400; }
/* 展开面板里的占位文案（WideIP 无关联池时） */
.panel-empty { padding: 4px 0; font-size: 13px; color: var(--el-text-color-secondary); }
</style>
