<script setup lang="ts">
import PageLayout from '@/layout/PageLayout.vue'
import DataTable from '@/components/DataTable.vue'
import DataColumn from '@/components/DataColumn.vue'
import { TABLE_KEYS } from '@/constants/tableKeys'
import DataPagination from '@/components/DataPagination.vue'
import FilterBar from '@/components/FilterBar.vue'
import { useCrudApi } from '@/composables/useCrudApi'
import { getLtmChain } from '@/api/config'
import type { LbTreeRow, LtmChainPool, LtmChainRow } from '@/types'

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
  detail: [pool.mode, pool.monitors?.length ? `监控 ${pool.monitors.join('、')}` : '']
    .filter(Boolean)
    .join(' · '),
  children: members.map((m, idx) => ({
    // 成员唯一键是 设备+池名+名字+端口，这里挂在池下用序号即可
    id: `member-${device}-${pool.name}-${idx}`,
    kind: 'member' as const,
    label: m.address ? addrPort(m.address, m.port) : m.name,
    tipLines: [m.name],
    detail: '',
  })),
})

/** 关联链行 → 树行：VS 为根，池是它的 child，成员是池的 child */
const buildTree = (r: LtmChainRow): LbTreeRow => ({
  id: `vs-${r.device}-${r.name}`,
  kind: 'vs',
  // 透明 VS 没有地址时回退显示名字
  label: r.vs_address ? addrPort(r.vs_address, r.vs_port) : r.name,
  tipLines: r.vs_address ? [r.name] : [],
  detail: [r.protocol && `协议 ${r.protocol}`, r.snat_type && `SNAT ${r.snat_type}`, r.persist && `会话保持 ${r.persist}`]
    .filter(Boolean)
    .join(' · '),
  device: r.device_hostname,
  children: r.pool ? [buildPoolTree(r.device, r.pool, r.members)] : undefined,
})

const treeRows = computed(() => rows.value.map(buildTree))

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
        search-placeholder="搜索 名称/地址/地址:端口/池/成员IP:端口"
        search-width="220px"
      />
    </template>
    <div class="table-wrapper">
      <!-- 树形参数经 attrs 透传落到内层 el-table（组件注释里的既定机制）：row-key 必填，箭头/缩进自动加在第一列 -->
      <DataTable
        :table-key="TABLE_KEYS.slbVirtualServers"
        :data="treeRows"
        :loading="loading"
        row-key="id"
        :tree-props="{ children: 'children' }"
        default-expand-all
        size="small"
      >
        <!-- 名称列 = 树首列：主显示地址#端口，VS/池/成员的 name 收进 hover -->
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
        <DataColumn label="类型" column-key="kind" min-width="110">
          <template #default="{ row }">
            <el-tag :type="kindTagOf(row.kind)" size="small">{{ kindLabelOf(row.kind) }}</el-tag>
          </template>
        </DataColumn>
        <DataColumn prop="detail" label="详情" min-width="320">
          <template #default="{ row }">
            <span v-if="row.detail">{{ row.detail }}</span>
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
