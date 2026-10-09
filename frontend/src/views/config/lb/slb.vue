<script setup lang="ts">
import PageLayout from '@/layout/PageLayout.vue'
import { Download, Switch } from '@element-plus/icons-vue'
import DataTable from '@/components/DataTable.vue'
import DataColumn from '@/components/DataColumn.vue'
import { TABLE_KEYS } from '@/constants/tableKeys'
import DataPagination from '@/components/DataPagination.vue'
import FilterBar from '@/components/FilterBar.vue'
import { useCrudApi } from '@/composables/useCrudApi'
import { exportLtmChain, getLtmChain } from '@/api/config'
import type { LbMemberRow, LbPoolRow, LbRootRow, LtmChainPool, LtmChainRow, LtmFlatRow } from '@/types'

const filterDevice = ref<number | ''>('')

// 关联链聚合（/api/lb-chain/slb/）：每行一条 VS → 池 → 成员，
// 前端转成「根行（VS 自身字段）+ 展开面板（池 → 成员）」——两者各用各的列
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

const KIND_TAG = { vs: 'primary', pool: 'success', member: 'info', wideip: 'primary' } as const
const KIND_LABEL = { vs: '虚拟服务器', pool: '池', member: '成员', wideip: '' } as const
// 插槽 row 是 el-table 的 DefaultRow（any），索引前先收敛成 string，找不到就兜底
const kindTagOf = (kind: string) => KIND_TAG[kind as keyof typeof KIND_TAG] ?? 'info'
const kindLabelOf = (kind: string) => KIND_LABEL[kind as keyof typeof KIND_LABEL] ?? kind

/** 池及其成员 → pool 表行：`panel` 是该池的 member 表（严格依赖，展开池行才可见） */
const buildPoolPanel = (device: number, pool: LtmChainPool, members: LtmChainRow['members']): LbPoolRow => ({
  id: `pool-${device}-${pool.name}`,
  label: pool.name,
  algo: pool.mode || '',
  monitor: pool.monitors?.length ? pool.monitors.join('、') : '',
  panel: members.map((m, idx) => {
    const addr = m.address ? addrPort(m.address, m.port) : ''
    return {
      // 成员唯一键是 设备+池名+名字+端口，这里挂在池下用序号即可
      id: `member-${device}-${pool.name}-${idx}`,
      name: m.name || addr,
      // 名称里已经有地址时不再重复占一格
      address: m.name && addr && addr !== m.name ? addr : '',
    } as LbMemberRow
  }),
})

/** 关联链行 → 根行：VS 上主表，池/成员收进 panel 由展开列渲染 */
const buildRoot = (r: LtmChainRow): LbRootRow => ({
  id: `vs-${r.device}-${r.name}`,
  kind: 'vs',
  // 透明 VS 没有地址时回退显示名字
  label: r.vs_address ? addrPort(r.vs_address, r.vs_port) : r.name,
  // name 已升为独立列，hover 只补没上列的信息（SNAT 等次要字段）
  tipLines: [r.snat_type ? `SNAT：${r.snat_type}` : ''].filter(Boolean),
  device: r.device_hostname,
  vsName: r.name,
  protocol: r.protocol || '-',
  poolName: r.pool?.name || '-',
  profiles: r.profiles || [],
  persist: r.persist || '-',
  rules: r.rules || [],
  panel: r.pool ? [buildPoolPanel(r.device, r.pool, r.members)] : [],
})

const rootRows = computed(() => rows.value.map(buildRoot))

/** 导出扁平宽表为 xlsx（后端 openpyxl 生成、前端只下载 Blob；全量、带当前过滤/搜索） */
const exportLoading = ref(false)
const handleExport = async () => {
  exportLoading.value = true
  try {
    const res = await exportLtmChain({
      device: filterDevice.value || undefined,
      search: search.value || undefined,
    })
    const url = URL.createObjectURL(res.data as Blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `lb-chains-${new Date().toISOString().slice(0, 10)}.xlsx`
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
 * 有成员则每成员一行（VS + 池字段整条下填），池无成员则以池为行，
 * 无池则以 VS 为行；配合专属宽表列（SNAT/池模式/池监控…）融合成一张大表。
 */
const flatRows = computed(() => {
  const out: LtmFlatRow[] = []
  for (const r of rows.value) {
    const vsLabel = r.vs_address ? addrPort(r.vs_address, r.vs_port) : r.name
    const base = {
      device: r.device_hostname,
      vsLabel,
      vsName: r.name,
      protocol: r.protocol || '-',
      snat: r.snat_type || '-',
      persist: r.persist || '-',
      profiles: r.profiles || [],
      rules: r.rules || [],
      poolName: r.pool?.name || '-',
      poolMode: r.pool?.mode || '-',
      poolMonitors: r.pool?.monitors?.length ? r.pool.monitors.join('、') : '-',
    }
    const prefix = `flat-vs-${r.device}-${r.name}`
    if (r.pool && r.members.length) {
      r.members.forEach((m: LtmChainRow['members'][number], idx: number) =>
        out.push({
          ...base,
          id: `${prefix}-m${idx}`,
          kind: 'member',
          label: m.address ? addrPort(m.address, m.port) : m.name,
          tipLines: [m.name, `链路：${vsLabel} → ${r.pool!.name}`],
        }),
      )
    } else if (r.pool) {
      out.push({
        ...base,
        id: `${prefix}-p`,
        kind: 'pool',
        label: r.pool.name,
        tipLines: [`链路：${vsLabel}（池无成员，以池为行）`],
      })
    } else {
      out.push({
        ...base,
        id: `${prefix}-v`,
        kind: 'vs',
        label: vsLabel,
        tipLines: [r.snat_type ? `SNAT：${r.snat_type}` : ''].filter(Boolean),
      })
    }
  }
  return out
})

watch(filterDevice, resetAndFetch)
onMounted(loadRows)
</script>

<template>
  <PageLayout title="负载均衡管理">
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
        device-type="slb"
        search-placeholder="搜索 名称/地址/地址:端口/池/成员IP:端口"
        search-width="220px"
      />
    </template>
    <div class="table-wrapper">
      <!-- 展开列经 attrs 透传落到内层 el-table（组件注释里的既定机制）：row-key 必填；
           扁平视图没有展开列，主表只有一层叶子行 -->
      <DataTable
        :table-key="TABLE_KEYS.slbVirtualServers"
        :data="viewMode === 'detail' ? rootRows : flatRows"
        :loading="loading"
        row-key="id"
        size="small"
      >
        <!-- 主表列组：只放 VS 自身的字段；池 / 成员明细在展开面板里，与这些列完全无关 -->
        <template v-if="viewMode === 'detail'">
          <!-- 展开列：单元格只画箭头，面板内容跨整行渲染，不参与列宽/顺序/显隐偏好 -->
          <DataColumn type="expand" label="">
            <template #default="{ row }">
              <!-- 面板整体右移一个展开列宽（48px，与 DataColumn type=expand 的列宽同源）：
                   子表首列对齐主表第一列（名称），而不是箭头列 -->
              <div class="panel">
                <div v-if="!row.panel?.length" class="panel-empty">未关联池</div>
                <!-- pool 表：无表头，格子自带「字段名：」前缀；池行再展开一层才是 member 表 -->
                <el-table v-else :data="row.panel" row-key="id" :show-header="false" size="small">
                  <DataColumn type="expand" label="">
                    <template #default="{ row: p }">
                      <div class="panel">
                        <div v-if="!p.panel?.length" class="panel-empty">无成员</div>
                        <!-- member 表：同样无表头，字段名前缀与 pool 表一致 -->
                        <el-table v-else :data="p.panel" row-key="id" :show-header="false" size="small">
                          <DataColumn prop="name" column-key="mName" label="名称" min-width="200">
                            <template #default="{ row: m }">
                              <span class="cell-k">名称：</span><strong>{{ m.name }}</strong>
                            </template>
                          </DataColumn>
                          <DataColumn prop="address" column-key="mAddr" label="地址" min-width="170">
                            <template #default="{ row: m }">
                              <template v-if="m.address">
                                <span class="cell-k">地址：</span>{{ m.address }}
                              </template>
                            </template>
                          </DataColumn>
                        </el-table>
                      </div>
                    </template>
                  </DataColumn>
                  <DataColumn prop="label" column-key="poolLabel" label="池" min-width="220">
                    <template #default="{ row: p }">
                      <span class="cell-k">池：</span><strong>{{ p.label }}</strong>
                    </template>
                  </DataColumn>
                  <DataColumn prop="algo" column-key="poolAlgo" label="负载模式" min-width="150">
                    <template #default="{ row: p }">
                      <template v-if="p.algo">
                        <span class="cell-k">负载模式：</span>{{ p.algo }}
                      </template>
                    </template>
                  </DataColumn>
                  <DataColumn prop="monitor" column-key="poolMonitor" label="监控" min-width="170">
                    <template #default="{ row: p }">
                      <template v-if="p.monitor">
                        <span class="cell-k">监控：</span>{{ p.monitor }}
                      </template>
                    </template>
                  </DataColumn>
                </el-table>
              </div>
            </template>
          </DataColumn>
          <DataColumn prop="label" label="名称" min-width="240">
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
          <DataColumn label="类型" column-key="kind" min-width="90">
            <template #default="{ row }">
              <el-tag :type="kindTagOf(row.kind)" size="small">{{ kindLabelOf(row.kind) }}</el-tag>
            </template>
          </DataColumn>
          <!-- 以下六列全是 VS 自身的配置，根行独占；池 / 成员的字段一律不上主表 -->
          <DataColumn prop="vsName" label="VS名称" min-width="170" show-overflow-tooltip />
          <DataColumn prop="protocol" label="协议" min-width="70" />
          <DataColumn prop="poolName" label="关联池" min-width="140" />
          <DataColumn label="Profile" column-key="profiles" min-width="150">
            <template #default="{ row }">
              <span v-if="row.profiles?.length">{{ row.profiles.join('、') }}</span>
            </template>
          </DataColumn>
          <DataColumn prop="persist" label="会话保持" min-width="100" />
          <DataColumn label="iRule" column-key="rules" min-width="150">
            <template #default="{ row }">
              <span v-if="row.rules?.length">{{ row.rules.join('、') }}</span>
            </template>
          </DataColumn>
        </template>
        <!-- 扁平宽表列组：按链层级排序——VS 段 → 池段 → 成员段；SNAT/池负载模式/池监控一并上列 -->
        <template v-else>
          <DataColumn prop="device" label="设备" min-width="120" />
          <DataColumn prop="vsLabel" label="VS地址#端口" min-width="150" show-overflow-tooltip />
          <DataColumn prop="vsName" label="VS名称" min-width="170" show-overflow-tooltip />
          <DataColumn prop="protocol" label="协议" min-width="70" />
          <DataColumn prop="snat" label="SNAT" min-width="90" />
          <DataColumn prop="persist" label="会话保持" min-width="95" />
          <DataColumn label="Profile" column-key="profiles" min-width="150">
            <template #default="{ row }">
              <span v-if="row.profiles?.length">{{ row.profiles.join('、') }}</span>
            </template>
          </DataColumn>
          <DataColumn label="iRule" column-key="rules" min-width="150">
            <template #default="{ row }">
              <span v-if="row.rules?.length">{{ row.rules.join('、') }}</span>
            </template>
          </DataColumn>
          <DataColumn prop="poolName" label="关联池" min-width="130" />
          <DataColumn prop="poolMode" label="池负载模式" min-width="110" />
          <DataColumn prop="poolMonitors" label="池监控" min-width="140" />
          <DataColumn label="名称" column-key="label" min-width="220">
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
        </template>
      </DataTable>
    </div>
    <DataPagination v-model:page="page" v-model:page-size="pageSize" :total="total" @change="refetch" />
  </PageLayout>
</template>

<style scoped>
.table-wrapper { flex: 1; min-height: 0; background: var(--el-bg-color); border-radius: 8px; overflow: hidden; }
/* 展开面板：右移一个展开列宽（48px），子表首列与主表首列（名称）对齐 */
.panel { padding-left: 48px; }
/* 子表（pool / member 表）无表头：字段名前缀放进格子里，用次要色与值区分 */
.cell-k { color: var(--el-text-color-secondary); }
/* 展开面板里的占位文案（VS 未关联池时） */
.panel-empty { padding: 4px 0; font-size: 13px; color: var(--el-text-color-secondary); }
</style>
