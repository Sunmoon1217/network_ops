<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import PageLayout from '@/ui/PageLayout.vue'
import api from '@/api/index'

/** 设备下拉项（只列 GSLB 设备） */
interface DeviceOption {
  id: number
  hostname: string
  device_type: string
  device_type_display?: string
  security_zone_name?: string
}

/** LTM 池成员节点，nested 为级联到的下层 LTM 虚拟服务器 */
interface LtmMemberNode {
  name: string
  address: string
  port: string
  ip_port: string
  nested: LtmNode | null
  matched_ip_port: string
}

/** LTM 虚拟服务器节点（含池与池成员） */
interface LtmNode {
  device: string
  name: string
  vs_address: string
  vs_port: string
  status: string
  pool: string
  pool_found: boolean
  members: LtmMemberNode[]
}

/** GTM 虚拟服务器（GTM 池成员解析到的下一跳） */
interface GtmVServerNode {
  id: number
  name: string
  server_name: string
  ip_address: string
  port: string
  monitor: string
}

/** 链路解析三态：GTM VS 缺失 / 无对应 LTM VS / 完全解析 */
type MemberStatus = 'vserver_not_found' | 'ltm_not_found' | 'resolved' | ''

/** GTM 池成员节点 */
interface GtmMemberNode {
  server_name: string
  vs_name: string
  member_ref: string
  state: string
  order: number | null
  status: MemberStatus
  message: string
  vserver: GtmVServerNode | null
  ltm: LtmNode | null
  fallback_ip_port: string
}

/** GTM 池节点 */
interface GtmPoolNode {
  name: string
  found: boolean
  lb_mode: string
  members: GtmMemberNode[]
}

/** WideIP 节点 */
interface WideIpNode {
  id: number
  name: string
  rtype: string
  lb_mode: string
  pool_count: number
  pools: GtmPoolNode[]
}

/** 接口响应结构 */
interface AnalysisResult {
  device: { id: number; hostname: string; device_type: string }
  wideips: WideIpNode[]
}

/**
 * 扁平表格的一行：一条从 WideIP 到最终后端的完整链路。
 *
 * 与树形展示不同，每行自带全部层级信息，便于筛选、排序与对照；
 * LTM 分叉时同一条 GTM 成员会展开成多行。
 */
interface PathRow {
  key: string
  wideip: string
  wideipType: string
  pool: string
  poolFound: boolean
  member: string
  gtmVserver: string
  ltmChain: string
  backendMember: string
  finalAddress: string
  status: string
  statusCode: MemberStatus
  note: string
}

/** 状态对应的标签配色 */
type RowTone = 'success' | 'danger' | 'warning' | 'info'

const devices = ref<DeviceOption[]>([])
const selectedDevice = ref<number | null>(null)
const result = ref<AnalysisResult | null>(null)
const devicesLoading = ref(false)
const analysisLoading = ref(false)
const exportLoading = ref(false)

/** 拼 "ip:port"，端口为空时只返回 IP */
const joinIpPort = (ip: string | null | undefined, port: string | number | null | undefined) => {
  if (!ip) return ''
  return port ? `${ip}:${port}` : String(ip)
}

/** GTM 池成员按 order 排序（order 为空的排最后），不修改原数组 */
const sortMembers = (members: GtmMemberNode[]) =>
  members.slice().sort((a, b) => {
    const orderA = a.order === null || a.order === undefined ? Number.MAX_SAFE_INTEGER : a.order
    const orderB = b.order === null || b.order === undefined ? Number.MAX_SAFE_INTEGER : b.order
    return orderA - orderB
  })

/** 三态对应的文案 */
const statusLabel = (status: MemberStatus) => {
  if (status === 'resolved') return '已解析到后端'
  if (status === 'vserver_not_found') return 'GTM VS 未找到'
  if (status === 'ltm_not_found') return '无对应 LTM VS'
  return ''
}

/** 三态对应的标签类型 */
const statusTone = (status: MemberStatus): RowTone => {
  if (status === 'resolved') return 'success'
  if (status === 'vserver_not_found') return 'danger'
  if (status === 'ltm_not_found') return 'warning'
  return 'info'
}

/**
 * 沿 LTM 子树走到叶子，产出所有 (虚拟服务器链, 叶子成员, 最终地址)。
 *
 * 一个虚拟服务器可能有多个成员，成员又可能级联到下层虚拟服务器，所以这里返回
 * 的是**所有路径**；若某层没有成员，则该虚拟服务器自己就是终点。
 */
const walkLtmPaths = (node: LtmNode | null, prefix: string[]): [string[], LtmMemberNode | null, string][] => {
  if (!node) return []
  const chain = [...prefix, node.name || '']
  const members = node.members ?? []
  if (!members.length) return [[chain, null, joinIpPort(node.vs_address, node.vs_port)]]

  const paths: [string[], LtmMemberNode | null, string][] = []
  members.forEach((member) => {
    if (member.nested) {
      paths.push(...walkLtmPaths(member.nested, chain))
    } else {
      paths.push([chain, member, member.ip_port || joinIpPort(member.address, member.port)])
    }
  })
  return paths
}

/** 把分析结果扁平化成「一行一条链路」 */
const buildPathRows = (data: AnalysisResult | null): PathRow[] => {
  if (!data) return []
  const rows: PathRow[] = []

  data.wideips.forEach((wideip, wi) => {
    wideip.pools.forEach((pool, pi) => {
      const members = sortMembers(pool.members ?? [])
      const poolKey = `w${wi}-p${pi}`

      // 池没有成员时也保留一行，避免这条记录从表里凭空消失
      if (!members.length) {
        rows.push({
          key: `${poolKey}-empty`,
          wideip: wideip.name || '',
          wideipType: wideip.rtype || '',
          pool: pool.name || '',
          poolFound: pool.found,
          member: '',
          gtmVserver: '',
          ltmChain: '',
          backendMember: '',
          finalAddress: '',
          status: '',
          statusCode: '',
          note: pool.found ? '该池没有成员' : '池未找到',
        })
        return
      }

      members.forEach((member, mi) => {
        const memberKey = `${poolKey}-m${mi}`
        const ref = member.member_ref || `${member.server_name}:${member.vs_name}`
        const base = {
          wideip: wideip.name || '',
          wideipType: wideip.rtype || '',
          pool: pool.name || '',
          poolFound: pool.found,
          member: ref,
          gtmVserver: '',
          ltmChain: '',
          backendMember: '',
          finalAddress: '',
          status: statusLabel(member.status),
          statusCode: member.status,
          note: [member.state, member.order !== null && member.order !== undefined ? `order ${member.order}` : '']
            .filter(Boolean)
            .join(' · '),
        }

        // ① GTM 虚拟服务器缺失：链路在此中断
        if (member.status === 'vserver_not_found') {
          rows.push({
            ...base,
            key: memberKey,
            note: [base.note, member.message || '未找到'].filter(Boolean).join(' · '),
          })
          return
        }

        // GTM 虚拟服务器（下一跳）
        const vserver = member.vserver
        if (vserver) {
          const address = joinIpPort(vserver.ip_address, vserver.port)
          base.gtmVserver = address ? `${vserver.name || '-'}（${address}）` : vserver.name || ''
        }

        // ② 无对应 LTM 虚拟服务器：GTM VS 的 ip:port 就是最终地址
        if (member.status === 'ltm_not_found') {
          rows.push({
            ...base,
            key: `${memberKey}-fallback`,
            finalAddress: member.fallback_ip_port || '',
            note: [base.note, 'GTM 虚拟服务器地址即最终地址'].filter(Boolean).join(' · '),
          })
          return
        }

        // ③ 解析成功：LTM 子树的每条路径各占一行
        const paths = walkLtmPaths(member.ltm, [])
        if (!paths.length) {
          rows.push({ ...base, key: memberKey })
          return
        }
        paths.forEach(([chain, leaf, address], pathIndex) => {
          const chainNames = chain.filter(Boolean)
          rows.push({
            ...base,
            key: `${memberKey}-path${pathIndex}`,
            ltmChain: chainNames.join(' → '),
            backendMember: leaf?.name || '',
            finalAddress: address || '',
            note: chainNames.length > 1 ? [base.note, `级联 ${chainNames.length} 层`].filter(Boolean).join(' · ') : base.note,
          })
        })
      })
    })
  })

  return rows
}

/** 表格数据 */
const rows = computed<PathRow[]>(() => buildPathRows(result.value))

/** 统计各状态数量，展示在摘要条 */
const summary = computed(() => ({
  total: rows.value.length,
  resolved: rows.value.filter((row) => row.statusCode === 'resolved').length,
  broken: rows.value.filter((row) => row.statusCode === 'vserver_not_found').length,
  fallback: rows.value.filter((row) => row.statusCode === 'ltm_not_found').length,
}))

/** el-table 行 key */
const rowKey = (row: PathRow) => row.key

/** 下拉项文案 */
const deviceLabel = (device: DeviceOption) => {
  const zone = device.security_zone_name ? ` · ${device.security_zone_name}` : ''
  return `${device.hostname}${zone}`
}

/** 加载 GSLB 设备下拉（仅 gslb 类型） */
const fetchDevices = async () => {
  devicesLoading.value = true
  try {
    const res = await api.get('/api/assets/devices/', { params: { device_type: 'gslb', page_size: 500 } })
    devices.value = res.data?.results ?? res.data ?? []
  } catch (e: any) {
    devices.value = []
    ElMessage.error(e?.response?.data?.detail || '获取 GSLB 设备列表失败')
  } finally {
    devicesLoading.value = false
  }
}

/** 加载指定设备的 WideIP → 后端解析链路 */
const fetchAnalysis = async () => {
  if (!selectedDevice.value) {
    result.value = null
    return
  }
  analysisLoading.value = true
  try {
    const res = await api.get('/api/assets/internet-analysis/', { params: { device: selectedDevice.value } })
    result.value = res.data as AnalysisResult
  } catch (e: any) {
    result.value = null
    ElMessage.error(e?.response?.data?.error || '获取互联网资产分析失败')
  } finally {
    analysisLoading.value = false
  }
}

/** 刷新：设备列表与当前设备的分析结果一起重新拉取 */
const handleRefresh = async () => {
  await fetchDevices()
  await fetchAnalysis()
}

/**
 * 导出当前设备的分析结果为 xlsx。
 *
 * 文件由后端用 openpyxl 生成（前端因此不需要引入 xlsx 依赖），
 * 这里只负责把响应体当 Blob 下载。
 */
const handleExport = async () => {
  if (!selectedDevice.value) return
  exportLoading.value = true
  try {
    const res = await api.get('/api/assets/internet-analysis/export/', {
      params: { device: selectedDevice.value },
      responseType: 'blob',
    })
    const hostname = result.value?.device.hostname ?? 'export'
    const url = URL.createObjectURL(res.data as Blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `internet-asset-${hostname}.xlsx`
    link.click()
    URL.revokeObjectURL(url)
  } catch {
    ElMessage.error('导出失败')
  } finally {
    exportLoading.value = false
  }
}

watch(selectedDevice, () => {
  fetchAnalysis()
})

onMounted(() => {
  fetchDevices()
})
</script>

<template>
  <PageLayout title="互联网资产分析">
    <template #actions>
      <el-select
        v-model="selectedDevice"
        filterable
        clearable
        placeholder="选择 GSLB 设备"
        style="width: 240px"
        :loading="devicesLoading"
      >
        <el-option v-for="device in devices" :key="device.id" :label="deviceLabel(device)" :value="device.id" />
      </el-select>
      <el-button :disabled="!result" :loading="exportLoading" @click="handleExport">导出 xlsx</el-button>
      <el-button :loading="analysisLoading" @click="handleRefresh">刷新</el-button>
    </template>

    <div v-loading="analysisLoading" class="analysis-body">
      <el-empty v-if="!selectedDevice" description="请选择一个 GSLB 设备，查看域名到最终后端的解析链路" />
      <el-empty v-else-if="result && !result.wideips.length" description="该设备没有配置 WideIP" />

      <template v-else-if="result">
        <div class="summary-bar">
          <span class="summary-host">{{ result.device.hostname }}</span>
          <el-tag size="small" type="info">{{ result.device.device_type }}</el-tag>
          <span class="muted">WideIP {{ result.wideips.length }} 个 · 链路 {{ summary.total }} 条</span>
          <span class="legend">
            <el-tag size="small" type="success">已解析 {{ summary.resolved }}</el-tag>
            <el-tag size="small" type="danger">GTM VS 未找到 {{ summary.broken }}</el-tag>
            <el-tag size="small" type="warning">无对应 LTM VS {{ summary.fallback }}</el-tag>
          </span>
        </div>

        <el-table :data="rows" size="small" :row-key="rowKey" class="asset-table" border>
          <el-table-column prop="wideip" label="WideIP" min-width="200" fixed show-overflow-tooltip>
            <template #default="{ row }">
              <span class="mono strong">{{ row.wideip || '-' }}</span>
              <el-tag v-if="row.wideipType" size="small" type="info" class="inline-tag">{{ row.wideipType }}</el-tag>
            </template>
          </el-table-column>

          <el-table-column prop="pool" label="GTM 池" min-width="170" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.pool" class="mono">{{ row.pool }}</span>
              <span v-else class="muted">-</span>
              <el-tag v-if="row.pool && !row.poolFound" size="small" type="warning" class="inline-tag">未找到</el-tag>
            </template>
          </el-table-column>

          <el-table-column prop="member" label="GTM 成员" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.member" class="mono">{{ row.member }}</span>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>

          <el-table-column prop="gtmVserver" label="GTM 虚拟服务器" min-width="240" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.gtmVserver" class="mono">{{ row.gtmVserver }}</span>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>

          <el-table-column prop="ltmChain" label="LTM 链路" min-width="240" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.ltmChain" class="mono">{{ row.ltmChain }}</span>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>

          <el-table-column prop="backendMember" label="后端成员" min-width="170" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.backendMember" class="mono">{{ row.backendMember }}</span>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>

          <el-table-column prop="finalAddress" label="最终地址" min-width="170">
            <template #default="{ row }">
              <span v-if="row.finalAddress" class="mono strong">{{ row.finalAddress }}</span>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>

          <el-table-column prop="status" label="状态" min-width="150">
            <template #default="{ row }">
              <el-tag v-if="row.status" size="small" :type="statusTone(row.statusCode)">{{ row.status }}</el-tag>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>

          <el-table-column prop="note" label="说明" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.note" class="muted">{{ row.note }}</span>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>
        </el-table>
      </template>

      <el-empty v-else description="暂无分析结果，请点击刷新重试" />
    </div>
  </PageLayout>
</template>

<style scoped>
.analysis-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.summary-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  padding: 10px 14px;
  border-radius: 10px;
  background: rgba(52, 200, 255, 0.04);
  border: 1px solid rgba(52, 200, 255, 0.15);
}
.summary-host { font-size: 14px; font-weight: 600; }
.legend { display: flex; align-items: center; gap: 6px; margin-left: auto; }

.asset-table { width: 100%; }
.inline-tag { margin-left: 6px; }

.mono { font-family: Menlo, Consolas, monospace; font-size: 12px; }
.strong { font-weight: 600; }
.muted { font-size: 12px; color: var(--el-text-color-secondary); }
</style>
