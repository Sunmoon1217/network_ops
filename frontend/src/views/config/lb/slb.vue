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
import type { LbTreeRow, LtmChainPool, LtmChainRow, LtmFlatRow } from '@/types'

const filterDevice = ref<number | ''>('')

// 关联链聚合（/api/lb-chain/slb/）：每行一条 VS → 池 → 成员，前端再转成树形分级展示
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

/** 池及其成员 → 池行（成员是池的 children） */
const buildPoolTree = (device: number, pool: LtmChainPool, members: LtmChainRow['members']): LbTreeRow => ({
  id: `pool-${device}-${pool.name}`,
  kind: 'pool',
  label: pool.name,
  tipLines: [
    `负载模式：${pool.mode || '-'}`,
    pool.monitors?.length ? `监控：${pool.monitors.join('、')}` : '',
  ].filter(Boolean),
  children: members.map((m, idx) => ({
    // 成员唯一键是 设备+池名+名字+端口，这里挂在池下用序号即可
    id: `member-${device}-${pool.name}-${idx}`,
    kind: 'member' as const,
    label: m.address ? addrPort(m.address, m.port) : m.name,
    tipLines: [m.name],
  })),
})

/** 关联链行 → 树行：VS 为根，池是它的 child，成员是池的 child */
const buildTree = (r: LtmChainRow): LbTreeRow => ({
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
  children: r.pool ? [buildPoolTree(r.device, r.pool, r.members)] : undefined,
})

const treeRows = computed(() => rows.value.map(buildTree))

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

/** 视图模式：树形（分级展开）⇄ 扁平（join 宽表，以叶子为行、字段下填），两模式各配各的列 */
const viewMode = ref<'tree' | 'flat'>('tree')
const toggleView = () => (viewMode.value = viewMode.value === 'tree' ? 'flat' : 'tree')

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
        切换{{ viewMode === 'tree' ? '扁平' : '树形' }}视图
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
      <!-- 树形参数经 attrs 透传落到内层 el-table（组件注释里的既定机制）：row-key 必填，箭头/缩进自动加在第一列；
           扁平行没有 children（join 展开行），el-table 视其为叶子即自然平铺 -->
      <DataTable
        :table-key="TABLE_KEYS.slbVirtualServers"
        :data="viewMode === 'tree' ? treeRows : flatRows"
        :loading="loading"
        row-key="id"
        :tree-props="{ children: 'children' }"
        default-expand-all
        size="small"
      >
        <!-- 树形列组：分级展示，VS/池/成员的 name 收进 hover -->
        <template v-if="viewMode === 'tree'">
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
          <!-- 以下六列：VS 行填自身配置；池/成员行留空，层级聚焦在 VS 自身的配置上 -->
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
.table-wrapper { flex: 1; min-height: 0; background: #fff; border-radius: 8px; overflow: hidden; }
</style>
