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
  llbMemberAddress: string
  llbMemberPort: string
  slbAddress: string
  slbPort: string
  slbMemberAddress: string
  slbMemberPort: string
  note: string
}

/** 路径的一级：本级虚拟服务器 + 指向下一级的池成员（终点时为 null） */
type LtmStep = [LtmNode, LtmMemberNode | null]

/** 一个空行骨架，避免每处都写全 13 个字段 */
const blankRow = (wideip: string, rtype: string): Omit<PathRow, 'key'> => ({
  wideip,
  rtype,
  gtmIp: '',
  gtmPort: '',
  llbAddress: '',
  llbPort: '',
  llbMemberAddress: '',
  llbMemberPort: '',
  slbAddress: '',
  slbPort: '',
  slbMemberAddress: '',
  slbMemberPort: '',
  note: '',
})

const devices = ref<DeviceOption[]>([])
const selectedDevice = ref<number | null>(null)
const result = ref<AnalysisResult | null>(null)
const devicesLoading = ref(false)
const analysisLoading = ref(false)
const exportLoading = ref(false)

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
            <el-tag size="small" type="success">已解析到 LLB {{ summary.resolved }}</el-tag>
            <el-tag size="small" type="danger">GTM VS 未找到 {{ summary.broken }}</el-tag>
            <el-tag size="small" type="warning">无对应 LTM VS {{ summary.fallback }}</el-tag>
          </span>
        </div>

        <el-table :data="rows" size="small" :row-key="rowKey" class="asset-table" border>
          <el-table-column prop="wideip" label="域名" min-width="200" fixed show-overflow-tooltip>
            <template #default="{ row }">
              <span class="mono strong">{{ row.wideip || '-' }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="rtype" label="类型" width="70" />

          <el-table-column label="GTM 虚拟服务器" align="center">
            <el-table-column prop="gtmIp" label="IP" min-width="130">
              <template #default="{ row }">
                <span v-if="row.gtmIp" class="mono">{{ row.gtmIp }}</span>
                <span v-else class="muted">-</span>
              </template>
            </el-table-column>
            <el-table-column prop="gtmPort" label="端口" width="80" />
          </el-table-column>

          <el-table-column label="LLB（第一级 LTM）" align="center">
            <el-table-column label="虚拟服务器" align="center">
              <el-table-column prop="llbAddress" label="地址" min-width="130">
                <template #default="{ row }">
                  <span v-if="row.llbAddress" class="mono">{{ row.llbAddress }}</span>
                  <span v-else class="muted">-</span>
                </template>
              </el-table-column>
              <el-table-column prop="llbPort" label="端口" width="80" />
            </el-table-column>
            <el-table-column label="后端成员" align="center">
              <el-table-column prop="llbMemberAddress" label="地址" min-width="130">
                <template #default="{ row }">
                  <span v-if="row.llbMemberAddress" class="mono">{{ row.llbMemberAddress }}</span>
                  <span v-else class="muted">-</span>
                </template>
              </el-table-column>
              <el-table-column prop="llbMemberPort" label="端口" width="80" />
            </el-table-column>
          </el-table-column>

          <el-table-column label="SLB（下级 LTM）" align="center">
            <el-table-column label="虚拟服务器" align="center">
              <el-table-column prop="slbAddress" label="地址" min-width="130">
                <template #default="{ row }">
                  <span v-if="row.slbAddress" class="mono">{{ row.slbAddress }}</span>
                  <span v-else class="muted">-</span>
                </template>
              </el-table-column>
              <el-table-column prop="slbPort" label="端口" width="80" />
            </el-table-column>
            <el-table-column label="后端成员" align="center">
              <el-table-column prop="slbMemberAddress" label="地址" min-width="130">
                <template #default="{ row }">
                  <span v-if="row.slbMemberAddress" class="mono">{{ row.slbMemberAddress }}</span>
                  <span v-else class="muted">-</span>
                </template>
              </el-table-column>
              <el-table-column prop="slbMemberPort" label="端口" width="80" />
            </el-table-column>
          </el-table-column>

          <el-table-column prop="note" label="说明" min-width="220" show-overflow-tooltip>
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

.mono { font-family: Menlo, Consolas, monospace; font-size: 12px; }
.strong { font-weight: 600; }
.muted { font-size: 12px; color: var(--el-text-color-secondary); }
</style>
