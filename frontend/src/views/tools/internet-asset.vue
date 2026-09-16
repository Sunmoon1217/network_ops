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

/**
 * LTM 子树拍平后的一行：用 depth 缩进体现层级，
 * 这样单文件内即可展示任意深度的级联，无需额外的递归组件。
 */
interface LtmRow {
  key: string
  kind: 'vs' | 'member'
  depth: number
  name: string
  address: string
  device: string
  status: string
  pool: string
  poolFound: boolean
  matched: string
  isLeaf: boolean
}

/** 视图模型：成员上挂载已拍平的 LTM 行 */
interface MemberView extends GtmMemberNode {
  ltmRows: LtmRow[]
}

interface PoolView extends Omit<GtmPoolNode, 'members'> {
  members: MemberView[]
}

interface WideIpView extends Omit<WideIpNode, 'pools'> {
  pools: PoolView[]
}

const devices = ref<DeviceOption[]>([])
const selectedDevice = ref<number | null>(null)
const result = ref<AnalysisResult | null>(null)
const devicesLoading = ref(false)
const analysisLoading = ref(false)

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

/** 把 LTM 子树拍平成带 depth 的行：LTM VS → Pool Member → 级联 LTM VS … */
const flattenLtm = (node: LtmNode | null, depth = 0, prefix = ''): LtmRow[] => {
  if (!node) return []
  const rows: LtmRow[] = [
    {
      key: `${prefix}vs`,
      kind: 'vs',
      depth,
      name: node.name || '(未命名虚拟服务器)',
      address: joinIpPort(node.vs_address, node.vs_port),
      device: node.device || '',
      status: node.status || '',
      pool: node.pool || '',
      poolFound: node.pool_found,
      matched: '',
      isLeaf: false,
    },
  ]
  node.members.forEach((member, index) => {
    const key = `${prefix}m${index}`
    rows.push({
      key,
      kind: 'member',
      depth: depth + 1,
      name: member.name || '(未命名成员)',
      address: member.ip_port || joinIpPort(member.address, member.port),
      device: '',
      status: '',
      pool: '',
      poolFound: false,
      matched: member.matched_ip_port || '',
      // 没有下级虚拟服务器的成员就是链路终点
      isLeaf: !member.nested,
    })
    // 命中下层 LTM VS 时继续展开（缩进再进一级）
    if (member.nested) rows.push(...flattenLtm(member.nested, depth + 2, `${key}-`))
  })
  return rows
}

/** 视图模型：为每个 GTM 成员预计算拍平后的 LTM 行 */
const wideipViews = computed<WideIpView[]>(() =>
  (result.value?.wideips ?? []).map((wideip) => ({
    ...wideip,
    pools: wideip.pools.map((pool) => ({
      ...pool,
      members: sortMembers(pool.members ?? []).map((member) => ({ ...member, ltmRows: flattenLtm(member.ltm) })),
    })),
  }))
)

/** 三态对应的标签类型：成功 / 警告（红） / 信息 */
const statusTagType = (status: MemberStatus): 'success' | 'danger' | 'info' => {
  if (status === 'resolved') return 'success'
  if (status === 'vserver_not_found') return 'danger'
  return 'info'
}

/** 三态对应的文案 */
const statusLabel = (status: MemberStatus) => {
  if (status === 'resolved') return '已解析到后端'
  if (status === 'vserver_not_found') return 'GTM 虚拟服务器未找到'
  if (status === 'ltm_not_found') return '无对应 LTM 虚拟服务器'
  return '未知'
}

/** GTM 虚拟服务器的 ip:port */
const vserverAddress = (member: GtmMemberNode) => joinIpPort(member.vserver?.ip_address, member.vserver?.port)

/** el-table 行 key */
const rowKey = (row: LtmRow) => row.key

/** 下拉项文案 */
const deviceLabel = (device: DeviceOption) => {
  const zone = device.security_zone_name ? ` · ${device.security_zone_name}` : ''
  return `${device.hostname}${zone}`
}

/** 加载 GSLB 设备下拉（仅 loadbalancer 类型） */
const fetchDevices = async () => {
  devicesLoading.value = true
  try {
    const res = await api.get('/api/assets/devices/', { params: { device_type: 'loadbalancer', page_size: 500 } })
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
      <el-button :loading="analysisLoading" @click="handleRefresh">刷新</el-button>
    </template>

    <div v-loading="analysisLoading" class="analysis-body">
      <el-empty v-if="!selectedDevice" description="请选择一个 GSLB 设备，查看域名到最终后端的解析链路" />
      <el-empty v-else-if="result && !result.wideips.length" description="该设备没有配置 WideIP" />

      <template v-else-if="result">
        <div class="summary-bar">
          <span class="summary-host">{{ result.device.hostname }}</span>
          <el-tag size="small" type="info">{{ result.device.device_type }}</el-tag>
          <span class="muted">共 {{ result.wideips.length }} 个 WideIP</span>
          <span class="legend">
            <el-tag size="small" type="success">已解析到后端</el-tag>
            <el-tag size="small" type="danger">GTM VS 未找到</el-tag>
            <el-tag size="small" type="info">无对应 LTM VS</el-tag>
          </span>
        </div>

        <!-- 第一层：WideIP（域名） -->
        <el-card v-for="wideip in wideipViews" :key="wideip.id" shadow="never" class="wideip-card">
          <template #header>
            <div class="wideip-title">
              <span class="wideip-name">{{ wideip.name }}</span>
              <el-tag size="small" type="info">{{ wideip.rtype }}</el-tag>
              <el-tag v-if="wideip.lb_mode" size="small">{{ wideip.lb_mode }}</el-tag>
              <span class="muted">池 {{ wideip.pool_count }} 个</span>
            </div>
          </template>

          <el-empty v-if="!wideip.pools.length" description="该 WideIP 没有池" :image-size="50" />

          <!-- 第二层：Pool（GTM 池） -->
          <div
            v-for="pool in wideip.pools"
            :key="pool.name"
            class="pool-card"
            :class="{ 'pool-missing': !pool.found }"
          >
            <div class="pool-header">
              <span class="node-tag pool-tag">POOL</span>
              <span class="mono strong">{{ pool.name }}</span>
              <el-tag v-if="!pool.found" size="small" type="warning">池未找到</el-tag>
              <el-tag v-else size="small" type="success">池已找到</el-tag>
              <el-tag v-if="pool.lb_mode" size="small" type="info">{{ pool.lb_mode }}</el-tag>
              <span class="muted">成员 {{ pool.members.length }} 个</span>
            </div>

            <el-empty v-if="!pool.members.length" description="该池没有成员" :image-size="40" />

            <!-- 第三层：GTM 池成员 → GTM VS → LTM 子树 -->
            <div
              v-for="member in pool.members"
              :key="member.member_ref || `${member.server_name}:${member.vs_name}`"
              class="member-card"
              :class="`member-${member.status || 'unknown'}`"
            >
              <div class="member-header">
                <span class="node-tag gtm-tag">GTM Member</span>
                <span class="mono strong">{{ member.member_ref || '-' }}</span>
                <el-tag size="small" :type="statusTagType(member.status)">{{ statusLabel(member.status) }}</el-tag>
                <el-tag v-if="member.state" size="small" type="info">{{ member.state }}</el-tag>
                <span v-if="member.order !== null && member.order !== undefined" class="muted">order {{ member.order }}</span>
              </div>

              <!-- ① GTM 虚拟服务器缺失：链路在此中断 -->
              <el-alert
                v-if="member.status === 'vserver_not_found'"
                type="error"
                :closable="false"
                show-icon
                :title="`GTM 虚拟服务器未找到（${member.message || '未找到'}）`"
                description="该池成员在 GTM 虚拟服务器表中不存在，无法继续解析到 LTM。"
              />

              <template v-else>
                <!-- ② GTM 虚拟服务器（下一跳） -->
                <div v-if="member.vserver" class="hop-row">
                  <span class="node-tag gtm-vs-tag">GTM VS</span>
                  <span class="mono">{{ member.vserver.name || '-' }}</span>
                  <span class="muted">server</span>
                  <span class="mono">{{ member.vserver.server_name || '-' }}</span>
                  <span class="muted">ip:port</span>
                  <span class="mono strong">{{ vserverAddress(member) || '-' }}</span>
                  <span v-if="member.vserver.monitor" class="muted">monitor {{ member.vserver.monitor }}</span>
                </div>

                <!-- ③ 无对应 LTM VS：GTM VS 的 ip:port 就是最终地址 -->
                <div v-if="member.status === 'ltm_not_found'" class="final-row">
                  <span class="muted">未匹配到 LTM 虚拟服务器</span>
                  <el-tag size="small" type="warning">最终地址</el-tag>
                  <span class="mono strong">{{ member.fallback_ip_port || vserverAddress(member) || '-' }}</span>
                </div>

                <!-- ④ 解析成功：展开 LTM VS → 池 → 成员 → 级联 VS -->
                <template v-else-if="member.ltm">
                  <div class="arrow">↓ LTM</div>
                  <el-table :data="member.ltmRows" size="small" :row-key="rowKey" class="ltm-table">
                    <el-table-column label="层级 / 对象" min-width="300">
                      <template #default="{ row }">
                        <div class="tree-cell" :style="{ paddingLeft: `${row.depth * 18}px` }">
                          <span class="node-tag" :class="row.kind === 'vs' ? 'ltm-vs-tag' : 'ltm-member-tag'">
                            {{ row.kind === 'vs' ? 'LTM VS' : 'Pool Member' }}
                          </span>
                          <span class="mono">{{ row.name }}</span>
                          <el-tag v-if="row.kind === 'member' && row.isLeaf" size="small" type="success">最终地址</el-tag>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column label="地址 / 端口" min-width="180">
                      <template #default="{ row }">
                        <span class="mono">{{ row.address || '-' }}</span>
                        <el-tag v-if="row.matched" size="small" type="warning" class="inline-tag">级联命中</el-tag>
                      </template>
                    </el-table-column>
                    <el-table-column label="LTM 设备" width="130">
                      <template #default="{ row }">
                        <span class="mono">{{ row.device || '-' }}</span>
                      </template>
                    </el-table-column>
                    <el-table-column label="状态 / 池" min-width="240">
                      <template #default="{ row }">
                        <template v-if="row.kind === 'vs'">
                          <el-tag v-if="row.status" size="small" :type="row.status === 'enabled' ? 'success' : 'info'">
                            {{ row.status }}
                          </el-tag>
                          <template v-if="row.pool">
                            <span class="mono">{{ row.pool }}</span>
                            <el-tag size="small" :type="row.poolFound ? 'success' : 'danger'">
                              {{ row.poolFound ? '池已找到' : '池未找到' }}
                            </el-tag>
                          </template>
                        </template>
                        <span v-else class="muted">-</span>
                      </template>
                    </el-table-column>
                    <el-table-column label="matched_ip_port" width="160">
                      <template #default="{ row }">
                        <span v-if="row.matched" class="mono">{{ row.matched }}</span>
                        <span v-else class="muted">-</span>
                      </template>
                    </el-table-column>
                  </el-table>
                </template>
              </template>
            </div>
          </div>
        </el-card>
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

.wideip-card { margin-bottom: 12px; }
.wideip-title { display: flex; align-items: center; gap: 8px; }
.wideip-name { font-size: 14px; font-weight: 600; }

.pool-card {
  padding: 10px 12px;
  margin-bottom: 10px;
  border: 1px solid var(--el-border-color-lighter);
  border-left: 3px solid var(--el-color-primary);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
}
.pool-card.pool-missing {
  border-left-color: var(--el-color-warning);
  background: var(--el-color-warning-light-9, rgba(230, 162, 60, 0.06));
}
.pool-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }

.member-card {
  padding: 10px 12px;
  margin-top: 8px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-light);
}
.member-card.member-vserver_not_found { border-color: var(--el-color-danger); }
.member-card.member-ltm_not_found { border-color: var(--el-color-info); }
.member-card.member-resolved { border-color: var(--el-color-success-light-5, var(--el-color-success)); }
.member-header { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }

.hop-row, .final-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.hop-row { margin-bottom: 6px; }
.final-row { padding: 6px 10px; border-radius: 6px; background: var(--el-color-warning-light-9); }
.arrow { margin: 4px 0; font-size: 12px; color: var(--el-text-color-secondary); }

.ltm-table { width: 100%; margin-top: 4px; }
.tree-cell { display: flex; align-items: center; gap: 6px; }
.inline-tag { margin-left: 6px; }

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
.pool-tag { background: var(--el-color-primary); }
.gtm-tag { background: var(--el-color-warning); }
.gtm-vs-tag { background: var(--el-color-warning-dark-2, #b88230); }
.ltm-vs-tag { background: var(--el-color-success); }
.ltm-member-tag { background: var(--el-color-info); }

.mono { font-family: Menlo, Consolas, monospace; font-size: 12px; }
.strong { font-weight: 600; }
.muted { font-size: 12px; color: var(--el-text-color-secondary); }
</style>
