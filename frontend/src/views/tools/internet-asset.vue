<script setup lang="ts">
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

/** 表格行的对象类型，决定标签文案与配色 */
type RowKind = 'wideip' | 'pool' | 'member' | 'vserver' | 'ltm_vs' | 'ltm_member'

/** 表格行的状态级别 */
type RowTone = 'success' | 'danger' | 'warning' | 'info' | ''

/**
 * 摊平后的一行。
 *
 * 整条链路（WideIP → Pool → GTM Member → GTM VS → LTM VS → Pool Member → 级联…）
 * 拍平成同一张表的行，用 depth 缩进体现层级，避免多层卡片嵌套。
 */
interface AssetRow {
  key: string
  depth: number
  kind: RowKind
  name: string
  address: string
  device: string
  status: string
  tone: RowTone
  note: string
  /** 链路终点（最终落到的后端地址） */
  isFinal: boolean
}

const devices = ref<DeviceOption[]>([])
const selectedDevice = ref<number | null>(null)
const result = ref<AnalysisResult | null>(null)
const devicesLoading = ref(false)
const analysisLoading = ref(false)
const exportLoading = ref(false)

/** 行类型对应的标签文案 */
const KIND_LABEL: Record<RowKind, string> = {
  wideip: 'WideIP',
  pool: 'GTM Pool',
  member: 'GTM Member',
  vserver: 'GTM VS',
  ltm_vs: 'LTM VS',
  ltm_member: 'Pool Member',
}

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

/** 三态对应的标签类型：成功 / 危险 / 信息 */
const statusTone = (status: MemberStatus): RowTone => {
  if (status === 'resolved') return 'success'
  if (status === 'vserver_not_found') return 'danger'
  if (status === 'ltm_not_found') return 'warning'
  return 'info'
}

/** 三态对应的文案 */
const statusLabel = (status: MemberStatus) => {
  if (status === 'resolved') return '已解析到后端'
  if (status === 'vserver_not_found') return 'GTM VS 未找到'
  if (status === 'ltm_not_found') return '无对应 LTM VS'
  return ''
}

/** GTM 虚拟服务器的 ip:port */
const vserverAddress = (member: GtmMemberNode) => joinIpPort(member.vserver?.ip_address, member.vserver?.port)

/**
 * 把 LTM 子树摊平成表格行：LTM VS → Pool Member → 级联 LTM VS …
 * nested 为下级虚拟服务器，逐级加深缩进。
 */
const flattenLtm = (node: LtmNode | null, depth: number, prefix: string): AssetRow[] => {
  if (!node) return []
  const rows: AssetRow[] = []

  rows.push({
    key: `${prefix}vs`,
    depth,
    kind: 'ltm_vs',
    name: node.name || '(未命名虚拟服务器)',
    address: joinIpPort(node.vs_address, node.vs_port),
    device: node.device || '',
    status: node.pool ? (node.pool_found ? '池已找到' : '池未找到') : '',
    tone: node.pool ? (node.pool_found ? 'success' : 'danger') : '',
    note: node.pool ? `池 ${node.pool}${node.status ? ` · ${node.status}` : ''}` : node.status || '',
    isFinal: false,
  })

  node.members.forEach((member, index) => {
    const key = `${prefix}m${index}`
    rows.push({
      key,
      depth: depth + 1,
      kind: 'ltm_member',
      name: member.name || '(未命名成员)',
      address: member.ip_port || joinIpPort(member.address, member.port),
      device: '',
      status: member.matched_ip_port ? '级联命中' : '',
      tone: member.matched_ip_port ? 'warning' : '',
      note: member.matched_ip_port ? `命中 ${member.matched_ip_port}` : '',
      // 没有下级虚拟服务器的成员就是链路终点
      isFinal: !member.nested,
    })
    // 命中下层 LTM VS 时继续展开（缩进再进一级）
    if (member.nested) rows.push(...flattenLtm(member.nested, depth + 1, `${key}-`))
  })

  return rows
}

/** 摊平整条链路：WideIP → Pool → Member → (GTM VS) → LTM 子树 */
const flattenResult = (data: AnalysisResult | null): AssetRow[] => {
  if (!data) return []
  const rows: AssetRow[] = []

  data.wideips.forEach((wideip, wi) => {
    const wiKey = `w${wi}`
    const meta = [wideip.rtype, wideip.lb_mode].filter(Boolean).join(' · ')
    rows.push({
      key: wiKey,
      depth: 0,
      kind: 'wideip',
      name: wideip.name || '(未命名域名)',
      address: '',
      device: '',
      status: `池 ${wideip.pool_count} 个`,
      tone: 'info',
      note: meta,
      isFinal: false,
    })

    wideip.pools.forEach((pool, pi) => {
      const poolKey = `${wiKey}-p${pi}`
      rows.push({
        key: poolKey,
        depth: 1,
        kind: 'pool',
        name: pool.name || '(未命名池)',
        address: '',
        device: '',
        status: pool.found ? '池已找到' : '池未找到',
        tone: pool.found ? 'success' : 'warning',
        note: [pool.lb_mode, `成员 ${pool.members.length} 个`].filter(Boolean).join(' · '),
        isFinal: false,
      })

      sortMembers(pool.members ?? []).forEach((member, mi) => {
        const memberKey = `${poolKey}-m${mi}`
        const ref = member.member_ref || `${member.server_name}:${member.vs_name}`
        rows.push({
          key: memberKey,
          depth: 2,
          kind: 'member',
          name: ref || '(未命名成员)',
          address: '',
          device: '',
          status: statusLabel(member.status),
          tone: statusTone(member.status),
          note: [member.state, member.order !== null && member.order !== undefined ? `order ${member.order}` : '']
            .filter(Boolean)
            .join(' · '),
          isFinal: false,
        })

        // ① GTM 虚拟服务器缺失：链路在此中断，没有后续行
        if (member.status === 'vserver_not_found') return

        // ② GTM 虚拟服务器（下一跳）
        if (member.vserver) {
          rows.push({
            key: `${memberKey}-vs`,
            depth: 3,
            kind: 'vserver',
            name: member.vserver.name || '(未命名)',
            address: vserverAddress(member),
            device: '',
            status: '',
            tone: '',
            note: [member.vserver.server_name && `server ${member.vserver.server_name}`, member.vserver.monitor && `monitor ${member.vserver.monitor}`]
              .filter(Boolean)
              .join(' · '),
            isFinal: false,
          })
        }

        // ③ 无对应 LTM VS：GTM VS 的 ip:port 就是最终地址
        if (member.status === 'ltm_not_found') {
          rows.push({
            key: `${memberKey}-final`,
            depth: 3,
            kind: 'vserver',
            name: '最终地址',
            address: member.fallback_ip_port || vserverAddress(member),
            device: '',
            status: '未匹配到 LTM 虚拟服务器',
            tone: 'warning',
            note: member.message,
            isFinal: true,
          })
          return
        }

        // ④ 解析成功：展开 LTM 子树
        if (member.ltm) rows.push(...flattenLtm(member.ltm, 3, `${memberKey}-`))
      })
    })
  })

  return rows
}

/** 表格数据 */
const rows = computed<AssetRow[]>(() => flattenResult(result.value))

/** 统计各状态数量，展示在摘要条 */
const summary = computed(() => {
  const all = rows.value
  return {
    total: all.length,
    resolved: all.filter((row) => row.kind === 'member' && row.tone === 'success').length,
    broken: all.filter((row) => row.kind === 'member' && row.tone === 'danger').length,
    fallback: all.filter((row) => row.kind === 'member' && row.tone === 'warning').length,
  }
})

/** el-table 行 key */
const rowKey = (row: AssetRow) => row.key

/**
 * 行缩进样式。
 *
 * el-table 插槽给出的行类型是 Element Plus 的 DefaultRow，拿不到我们自己的
 * AssetRow 类型，所以这里放宽参数类型，只取用 depth。
 */
const indent = (row: any) => ({ paddingLeft: `${row.depth * 18}px` })

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
          <span class="muted">WideIP {{ result.wideips.length }} 个 · 链路 {{ summary.total }} 行</span>
          <span class="legend">
            <el-tag size="small" type="success">已解析 {{ summary.resolved }}</el-tag>
            <el-tag size="small" type="danger">GTM VS 未找到 {{ summary.broken }}</el-tag>
            <el-tag size="small" type="warning">无对应 LTM VS {{ summary.fallback }}</el-tag>
          </span>
        </div>

        <el-table :data="rows" size="small" :row-key="rowKey" class="asset-table" border>
          <el-table-column label="层级 / 对象" min-width="320">
            <template #default="{ row }">
              <div class="tree-cell" :style="indent(row)">
                <span class="node-tag" :class="`kind-${row.kind}`">{{ KIND_LABEL[row.kind as RowKind] }}</span>
                <span class="mono" :class="{ strong: row.depth <= 1 }">{{ row.name }}</span>
                <el-tag v-if="row.isFinal" size="small" type="success">最终地址</el-tag>
              </div>
            </template>
          </el-table-column>

          <el-table-column label="地址 / 端口" min-width="180">
            <template #default="{ row }">
              <span v-if="row.address" class="mono">{{ row.address }}</span>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>

          <el-table-column label="LTM 设备" min-width="130">
            <template #default="{ row }">
              <span v-if="row.device" class="mono">{{ row.device }}</span>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>

          <el-table-column label="状态" min-width="170">
            <template #default="{ row }">
              <el-tag v-if="row.status" size="small" :type="row.tone || 'info'">{{ row.status }}</el-tag>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>

          <el-table-column label="说明" min-width="260">
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
.tree-cell { display: flex; align-items: center; gap: 6px; }

.node-tag {
  display: inline-block;
  padding: 1px 6px;
  font-size: 11px;
  line-height: 18px;
  border-radius: 4px;
  white-space: nowrap;
  color: #fff;
  background: var(--el-color-info);
}
.kind-wideip { background: var(--el-color-primary); }
.kind-pool { background: var(--el-color-warning); }
.kind-member { background: var(--el-color-warning-dark-2, #b88230); }
.kind-vserver { background: var(--el-color-info); }
.kind-ltm_vs { background: var(--el-color-success); }
.kind-ltm_member { background: var(--el-text-color-secondary); }

.mono { font-family: Menlo, Consolas, monospace; font-size: 12px; }
.strong { font-weight: 600; }
.muted { font-size: 12px; color: var(--el-text-color-secondary); }
</style>
