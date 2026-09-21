<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import PageLayout from '@/layout/PageLayout.vue'
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
  rules: string[]
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
  /** 链路最后的 IP（原始写法）→ 负责人，后端按 ServerOwner 现查，不随分析缓存过期 */
  owners?: Record<string, string>
}

/**
 * 表格的一行：一条从域名到最终后端的完整链路。
 *
 * 列固定为 GTM 四列 + LTM 两级（LLB / SLB）各四列 + 说明。
 * 注意 LTM 的两级并非数据库外键关系：GTM 虚拟服务器的 ip:port 命中某个
 * LTM 虚拟服务器即为 LLB，LLB 池成员的 address:port 再命中一个 LTM 虚拟服务器
 * 即为 SLB，任何一跳匹配不上对应的四列就留空。
 */
interface PathRow {
  key: string
  wideip: string
  rtype: string
  gtmIp: string
  gtmPort: string
  llbAddress: string
  llbPort: string
  /** 拼好的「地址:端口」，表格直接展示 */
  llbTarget: string
  llbRules: string
  llbMemberAddress: string
  llbMemberPort: string
  slbAddress: string
  slbPort: string
  slbTarget: string
  slbRules: string
  slbMemberAddress: string
  slbMemberPort: string
  /** 链路最后一跳的服务器「地址:端口」 */
  serverTarget: string
  owner: string
  note: string
}

/** 路径的一级：本级虚拟服务器 + 指向下一级的池成员（终点时为 null） */
type LtmStep = [LtmNode, LtmMemberNode | null]

/** 一个空行骨架，避免每处都写全所有字段 */
const blankRow = (wideip: string, rtype: string): Omit<PathRow, 'key'> => ({
  wideip,
  rtype,
  gtmIp: '',
  gtmPort: '',
  llbAddress: '',
  llbPort: '',
  llbTarget: '',
  llbRules: '',
  llbMemberAddress: '',
  llbMemberPort: '',
  slbAddress: '',
  slbPort: '',
  slbTarget: '',
  slbRules: '',
  slbMemberAddress: '',
  slbMemberPort: '',
  serverTarget: '',
  owner: '',
  note: '',
})

const devices = ref<DeviceOption[]>([])
const selectedDevice = ref<number | null>(null)
const result = ref<AnalysisResult | null>(null)
const devicesLoading = ref(false)
const analysisLoading = ref(false)
const exportLoading = ref(false)
const analyzedAt = ref('')

/** GTM 池成员按 order 排序（order 为空的排最后），不修改原数组 */
const sortMembers = (members: GtmMemberNode[]) =>
  members.slice().sort((a, b) => {
    const orderA = a.order === null || a.order === undefined ? Number.MAX_SAFE_INTEGER : a.order
    const orderB = b.order === null || b.order === undefined ? Number.MAX_SAFE_INTEGER : b.order
    return orderA - orderB
  })

/**
 * 沿 LTM 子树走到叶子，返回所有路径。
 *
 * 每条路径逐级记录 [本级虚拟服务器, 指向下一级的池成员]，调用方据此按级取字段
 * （第 0 级 = LLB，第 1 级 = SLB）。某级没有池成员时，该虚拟服务器自己就是终点。
 */
const walkLtmPaths = (node: LtmNode | null, prefix: LtmStep[]): LtmStep[][] => {
  if (!node) return []
  const members = node.members ?? []
  if (!members.length) return [[...prefix, [node, null]]]

  const paths: LtmStep[][] = []
  members.forEach((member) => {
    const step: LtmStep = [node, member]
    if (member.nested) {
      paths.push(...walkLtmPaths(member.nested, [...prefix, step]))
    } else {
      paths.push([...prefix, step])
    }
  })
  return paths
}

/** 取路径第 index 级的（虚拟服务器地址, 端口, 池成员地址, 池成员端口） */
const ltmColumns = (path: LtmStep[], index: number): [string, string, string, string] => {
  const step = path[index]
  if (!step) return ['', '', '', '']
  const [node, member] = step
  const address = node.vs_address || ''
  const port = node.vs_port || ''
  // 该级没有池成员，虚拟服务器自己就是终点
  if (!member) return [address, port, '', '']
  return [address, port, member.address || '', member.port || '']
}

/** 取路径第 index 级虚拟服务器的 iRules 文本 */
const ltmRules = (path: LtmStep[], index: number): string => {
  const step = path[index]
  if (!step) return ''
  return (step[0].rules ?? []).join(', ')
}

/**
 * 地址与端口的分隔符，与后端 `analysis.py` 的 TARGET_SEPARATOR 保持一致。
 *
 * 不用 ":"：IPv6 地址自带冒号，2001:db8::1:80 分不清哪段是端口。
 */
const TARGET_SEPARATOR = '#'

/** 拼成「地址#端口」，端口缺失时只显示地址 */
const formatTarget = (address: string, port: string): string =>
  address ? (port ? `${address}${TARGET_SEPARATOR}${port}` : address) : ''

/** 链路最后一跳的服务器「地址:端口」：两级取 SLB 池成员，一级取 LLB 池成员，断链时回退到 GTM */
const serverTargetOf = (row: PathRow): string => {
  if (row.slbMemberAddress) return formatTarget(row.slbMemberAddress, row.slbMemberPort)
  if (row.llbMemberAddress) return formatTarget(row.llbMemberAddress, row.llbMemberPort)
  return formatTarget(row.gtmIp, row.gtmPort)
}

/** 链路最后的 IP（只取地址），用于反查负责人 */
const finalIp = (row: PathRow): string =>
  row.slbMemberAddress || row.llbMemberAddress || row.gtmIp || ''

/** 把分析结果扁平化成「一行一条链路」 */
const buildPathRows = (data: AnalysisResult | null): PathRow[] => {
  if (!data) return []
  const rows: PathRow[] = []

  data.wideips.forEach((wideip, wi) => {
    const wideipName = wideip.name || ''
    const rtype = wideip.rtype || ''

    wideip.pools.forEach((pool, pi) => {
      const members = sortMembers(pool.members ?? [])
      const poolKey = `w${wi}-p${pi}`

      // 池没有成员时也保留一行，避免这条记录从表里凭空消失
      if (!members.length) {
        rows.push({
          ...blankRow(wideipName, rtype),
          key: `${poolKey}-empty`,
          note: pool.found ? `池 ${pool.name} 没有成员` : `池 ${pool.name} 未找到`,
        })
        return
      }

      members.forEach((member, mi) => {
        const memberKey = `${poolKey}-m${mi}`
        const base = blankRow(wideipName, rtype)
        const vserver = member.vserver
        if (vserver) {
          base.gtmIp = vserver.ip_address || ''
          base.gtmPort = vserver.port || ''
        }

        // ① GTM 虚拟服务器缺失：链路在此中断
        if (member.status === 'vserver_not_found') {
          rows.push({ ...base, key: memberKey, note: 'GTM 虚拟服务器未找到' })
          return
        }

        // ② 无对应 LTM 虚拟服务器：GTM VS 的地址即最终地址，LTM 两级留空
        if (member.status === 'ltm_not_found') {
          rows.push({ ...base, key: `${memberKey}-fallback`, note: '无对应 LTM 虚拟服务器，GTM 虚拟服务器地址即最终地址' })
          return
        }

        // ③ 解析成功：LTM 子树的每条路径各占一行
        const paths = walkLtmPaths(member.ltm, [])
        if (!paths.length) {
          rows.push({ ...base, key: memberKey })
          return
        }

        paths.forEach((path, pathIndex) => {
          const row = { ...base, key: `${memberKey}-path${pathIndex}` }
          ;[row.llbAddress, row.llbPort, row.llbMemberAddress, row.llbMemberPort] = ltmColumns(path, 0)
          ;[row.slbAddress, row.slbPort, row.slbMemberAddress, row.slbMemberPort] = ltmColumns(path, 1)
          row.llbRules = ltmRules(path, 0)
          row.slbRules = ltmRules(path, 1)
          if (path.length < 2) {
            row.note = '仅一级 LTM'
          } else if (path.length > 2) {
            // 表格只留两级，更深的级联在这里说明，避免信息凭空消失
            row.note = `还有 ${path.length - 2} 层级联未展开`
          }
          rows.push(row)
        })
      })
    })
  })

  // 负责人按链路最后的 IP 反查，与后端 build_path_rows 的回退顺序保持一致
  const owners = data.owners ?? {}
  rows.forEach((row) => {
    row.llbTarget = formatTarget(row.llbAddress, row.llbPort)
    row.slbTarget = formatTarget(row.slbAddress, row.slbPort)
    row.serverTarget = serverTargetOf(row)
    row.owner = owners[finalIp(row)] ?? ''
  })

  return rows
}

/** 表格数据 */
const rows = computed<PathRow[]>(() => buildPathRows(result.value))

/** 状态统计，展示在摘要条 */
const summary = computed(() => {
  const broken = rows.value.filter((row) => row.note.includes('GTM 虚拟服务器未找到')).length
  const fallback = rows.value.filter((row) => row.note.includes('无对应 LTM 虚拟服务器')).length
  const resolved = rows.value.filter((row) => row.llbAddress && !row.note.includes('未找到')).length
  return { total: rows.value.length, resolved, broken, fallback }
})

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
/**
 * 读取缓存的分析结果。
 *
 * 分析成本不低，接口只在手动「立即分析」时才真正计算；这里返回 404
 * 表示该设备还没分析过，属于正常状态而非错误，所以不弹提示。
 */
const loadCached = async () => {
  if (!selectedDevice.value) {
    result.value = null
    analyzedAt.value = ''
    return
  }
  analysisLoading.value = true
  try {
    const res = await api.get('/api/internet-analysis/', { params: { device: selectedDevice.value } })
    result.value = res.data as AnalysisResult
    analyzedAt.value = res.data?.analyzed_at ?? ''
  } catch (e: any) {
    result.value = null
    analyzedAt.value = ''
    // 404 = 尚未分析过，交给空状态提示；其余错误才弹窗
    if (e?.response?.status !== 404) {
      ElMessage.error(e?.response?.data?.error || '获取互联网资产分析失败')
    }
  } finally {
    analysisLoading.value = false
  }
}

/** 立即分析：触发后端重新计算并刷新缓存，然后展示新结果 */
const runAnalysis = async () => {
  if (!selectedDevice.value) return
  analysisLoading.value = true
  try {
    const res = await api.post('/api/internet-analysis/analyze/', null, {
      params: { device: selectedDevice.value },
    })
    result.value = res.data as AnalysisResult
    analyzedAt.value = res.data?.analyzed_at ?? ''
    ElMessage.success('分析完成')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '分析失败')
  } finally {
    analysisLoading.value = false
  }
}

/** 刷新：重拉设备列表，并重新读取当前设备的缓存结果（不触发分析） */
const handleRefresh = async () => {
  await fetchDevices()
  await loadCached()
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
    const res = await api.get('/api/internet-analysis/export/', {
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
  loadCached()
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
      <el-button type="primary" :disabled="!selectedDevice" :loading="analysisLoading" @click="runAnalysis">
        立即分析
      </el-button>
      <el-button :disabled="!result" :loading="exportLoading" @click="handleExport">导出 xlsx</el-button>
      <el-button :loading="analysisLoading" @click="handleRefresh">刷新</el-button>
    </template>

    <div v-loading="analysisLoading" class="analysis-body">
      <el-empty v-if="!selectedDevice" description="请选择一个 GSLB 设备，查看域名到最终后端的解析链路" />
      <el-empty v-else-if="!result" description="该设备尚未分析，点击右上角「立即分析」生成结果" />
      <el-empty v-else-if="!result.wideips.length" description="该设备没有配置 WideIP" />

      <template v-else-if="result">
        <div class="summary-bar">
          <span class="summary-host">{{ result.device.hostname }}</span>
          <el-tag size="small" type="info">{{ result.device.device_type }}</el-tag>
          <span class="muted">WideIP {{ result.wideips.length }} 个 · 链路 {{ summary.total }} 条</span>
          <span class="muted">分析于 {{ analyzedAt ? new Date(analyzedAt).toLocaleString() : "—" }}</span>
          <span class="legend">
            <el-tag size="small" type="success">已解析到 LLB {{ summary.resolved }}</el-tag>
            <el-tag size="small" type="danger">GTM VS 未找到 {{ summary.broken }}</el-tag>
            <el-tag size="small" type="warning">无对应 LTM VS {{ summary.fallback }}</el-tag>
          </span>
        </div>

        <el-table :data="rows" size="small" :row-key="rowKey" class="asset-table" border>
          <el-table-column prop="wideip" label="域名" width="240" fixed show-overflow-tooltip>
            <template #default="{ row }">
              <span class="mono strong">{{ row.wideip || '-' }}</span>
            </template>
          </el-table-column>

          <el-table-column label="LLB_VS地址#端口" width="200">
            <template #default="{ row }">
              <span v-if="row.llbTarget" class="mono">{{ row.llbTarget }}</span>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>

          <el-table-column prop="llbRules" label="LLB_Rule规则" width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.llbRules" class="mono">{{ row.llbRules }}</span>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>

          <el-table-column label="SLB_VS地址#端口" width="200">
            <template #default="{ row }">
              <span v-if="row.slbTarget" class="mono">{{ row.slbTarget }}</span>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>

          <el-table-column prop="slbRules" label="SLB_Rule规则" width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.slbRules" class="mono">{{ row.slbRules }}</span>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>

          <el-table-column label="服务器地址#端口" width="200">
            <template #default="{ row }">
              <span v-if="row.serverTarget" class="mono">{{ row.serverTarget }}</span>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>

          <el-table-column prop="owner" label="负责人" width="120">
            <template #default="{ row }">
              <span v-if="row.owner">{{ row.owner }}</span>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>
        </el-table>
      </template>

      <el-empty v-else description="暂无分析结果，请点击「立即分析」" />
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

.mono { font-family: Menlo, Consolas, monospace; font-size: 12px; }
.strong { font-weight: 600; }
.muted { font-size: 12px; color: var(--el-text-color-secondary); }
</style>
