<script setup lang="ts">
import PageLayout from '@/layout/PageLayout.vue'

const ipVer = ref<'v4' | 'v6'>('v4')
const input = ref('10.0.0.0/24')
const splitCount = ref<number | null>(null)
const hostCount = ref<number | null>(null)
const maskInput = ref('')
// 计算结果统一用 label -> value 的映射保存，便于按固定字段列表渲染占位
const results = ref<Record<string, string>>({})
const maskResults = ref<Record<string, string>>({})
const hostResults = ref<Record<string, string>>({})
const splits = ref<any[]>([])
const error = ref('')
const maskError = ref('')
const hostError = ref('')

// IPv6 特有功能：地址格式转换
const fmtInput = ref('2001:db8::1')
const fmtResults = ref<Record<string, string>>({})
// 二进制分组：8 组 × 16 位，与十六进制逐行对应
const fmtBinaryRows = ref<{ index: number; hex: string; binary: string }[]>([])
const fmtError = ref('')
// IPv6 特有功能：前缀规划
const planInput = ref('2001:db8::/32')
const planResults = ref<Record<string, string>>({})
const planExamples = ref<{ cidr: string; range: string }[]>([])
const planSamplePrefix = ref(64)
const planError = ref('')

// 占位符：所有字段始终渲染，未计算出的值用占位符显示
const PLACEHOLDER = '—'

// 各区展示字段（固定顺序，缺值走占位符，避免区块随结果出现/消失而跳动）
const IPV4_FIELDS = [
  '地址类型', '网络地址', '广播地址', '子网掩码', '通配符掩码', '十六进制',
  '总 IP', '可用 IP', '首可用', '末可用', '二进制掩码',
]
const IPV6_FIELDS = [
  '地址类型', '地址范围', '压缩格式', '展开格式', 'IPv4 映射', 'CIDR 前缀',
  '网络地址', '首可用 IP', '末可用 IP', '主机位数', '总 IP 数', 'PTR 域名',
]
const MASK_FIELDS = ['CIDR', '点分十进制', '十六进制', '二进制', '通配符掩码', '可用主机数']
const HOST_FIELDS = ['推荐 CIDR', '子网掩码', '实际可用']
const IPV6_FMT_FIELDS = ['完整格式', '压缩格式', '十六进制', '十进制']
const PLAN_FIELDS = ['输入前缀', '可划分 /48', '可划分 /56', '可划分 /64']

const resultFields = computed(() => (ipVer.value === 'v6' ? IPV6_FIELDS : IPV4_FIELDS))

const switchVer = () => {
  input.value = ipVer.value === 'v4' ? '10.0.0.0/24' : '2001:db8::/32'
  results.value = {}; splits.value = []; maskResults.value = {}; hostResults.value = {}
  error.value = ''; maskError.value = ''; hostError.value = ''
  splitCount.value = null; hostCount.value = null; maskInput.value = ''
  fmtInput.value = '2001:db8::1'; planInput.value = '2001:db8::/32'
  calcFormat(); calcPlan()
}

const calculate = () => {
  error.value = ''; results.value = {}; splits.value = []
  try { ipVer.value === 'v6' ? calcIPv6() : calcIPv4() } catch (e: any) { error.value = e.message || '计算错误' }
}

const calcMask = () => {
  maskResults.value = {}
  maskError.value = ''
  const val = maskInput.value.trim()
  if (!val) return
  if (val.startsWith('/')) {
    const prefix = parseInt(val.slice(1))
    if (isNaN(prefix) || prefix < 0 || prefix > 32) { maskError.value = 'CIDR 范围: 0-32'; return }
    const mask = prefix === 0 ? 0 : (~0 << (32 - prefix)) >>> 0
    maskResults.value = {
      'CIDR': `/${prefix}`,
      '点分十进制': numToIPv4(mask),
      '十六进制': '0x' + (mask >>> 0).toString(16).toUpperCase().padStart(8, '0'),
      '二进制': numToBinary(mask),
      '通配符掩码': numToIPv4((~mask) >>> 0),
      '可用主机数': (prefix >= 31 ? Math.pow(2, 32 - prefix) : Math.pow(2, 32 - prefix) - 2).toLocaleString(),
    }
  } else {
    const num = ipv4ToNum(val)
    if (num === null) { maskError.value = '无效的掩码格式'; return }
    const binary = num.toString(2).padStart(32, '0')
    if (!/^1*0*$/.test(binary)) { maskError.value = '不是合法子网掩码'; return }
    const prefix = binary.indexOf('0') === -1 ? 32 : binary.indexOf('0')
    maskResults.value = {
      'CIDR': `/${prefix}`,
      '点分十进制': val,
      '十六进制': '0x' + (num >>> 0).toString(16).toUpperCase().padStart(8, '0'),
      '二进制': numToBinary(num),
      '通配符掩码': numToIPv4((~num) >>> 0),
      '可用主机数': (prefix >= 31 ? Math.pow(2, 32 - prefix) : Math.pow(2, 32 - prefix) - 2).toLocaleString(),
    }
  }
}

const calcHosts = () => {
  hostResults.value = {}
  hostError.value = ''
  if (!hostCount.value || hostCount.value < 1) return
  const needed = hostCount.value + 2
  const bits = Math.ceil(Math.log2(needed))
  const prefix = 32 - bits
  if (prefix < 0) { hostError.value = '超出范围'; return }
  const mask = prefix === 0 ? 0 : (~0 << (32 - prefix)) >>> 0
  hostResults.value = {
    '推荐 CIDR': `/${prefix}`,
    '子网掩码': numToIPv4(mask),
    '实际可用': (Math.pow(2, bits) - 2).toLocaleString(),
  }
}

const calcIPv4 = () => {
  const parts = input.value.trim().split('/')
  if (parts.length !== 2) { error.value = '格式: IP/CIDR'; return }
  const ip = parts[0]
  const prefix = parseInt(parts[1])
  if (isNaN(prefix) || prefix < 0 || prefix > 32) { error.value = 'CIDR 范围: 0-32'; return }
  const ipNum = ipv4ToNum(ip)
  if (ipNum === null) { error.value = '无效 IPv4'; return }
  const mask = prefix === 0 ? 0 : (~0 << (32 - prefix)) >>> 0
  const wildcard = (~mask) >>> 0
  const network = (ipNum & mask) >>> 0
  const broadcast = (network | ~mask) >>> 0
  const total = broadcast - network + 1
  const usable = total >= 2 ? total - 2 : total
  results.value = {
    '地址类型': ipv4Type(ipNum),
    '网络地址': numToIPv4(network),
    '广播地址': numToIPv4(broadcast),
    '子网掩码': `${numToIPv4(mask)}  /${prefix}`,
    '通配符掩码': numToIPv4(wildcard),
    '十六进制': '0x' + (mask >>> 0).toString(16).toUpperCase().padStart(8, '0'),
    '总 IP': total.toLocaleString(),
    '可用 IP': usable.toLocaleString(),
    '首可用': total >= 2 ? numToIPv4(network + 1) : '',
    '末可用': total >= 2 ? numToIPv4(broadcast - 1) : '',
    '二进制掩码': numToBinary(mask),
  }
  if (splitCount.value && splitCount.value > 1) {
    const newPrefix = prefix + Math.ceil(Math.log2(splitCount.value))
    if (newPrefix > 32) { error.value = '拆分数超出范围'; return }
    const blockSize = Math.pow(2, 32 - newPrefix)
    for (let i = 0; i < Math.min(splitCount.value, 32); i++) {
      const subNet = (network + i * blockSize) >>> 0
      const subBcast = (subNet + blockSize - 1) >>> 0
      splits.value.push({ cidr: `${numToIPv4(subNet)}/${newPrefix}`, range: `${numToIPv4(subNet + 1)} — ${numToIPv4(subBcast - 1)}`, hosts: (blockSize - 2).toLocaleString() })
    }
  }
}

const calcIPv6 = () => {
  const parts = input.value.trim().split('/')
  if (parts.length !== 2) { error.value = '格式: IPv6/CIDR'; return }
  const ip = parts[0]
  const prefix = parseInt(parts[1])
  if (isNaN(prefix) || prefix < 0 || prefix > 128) { error.value = 'CIDR 范围: 0-128'; return }
  const expanded = parseIPv6(ip)
  if (!expanded) { error.value = '无效 IPv6'; return }
  const addrBigInt = ipv6ToBigInt(expanded)
  const maskBigInt = prefix === 0 ? 0n : ((1n << 128n) - (1n << BigInt(128 - prefix)))
  const networkBigInt = addrBigInt & maskBigInt
  const hostBits = 128 - prefix
  const totalHosts = hostBits <= 53 ? (BigInt(2) ** BigInt(hostBits)).toLocaleString() : `2^${hostBits}`
  const lastAddr = prefix === 0 ? (1n << 128n) - 1n : networkBigInt | ((1n << BigInt(hostBits)) - 1n)
  const networkHex = bigIntToIPv6(networkBigInt).replace(/:/g, '')
  const nibbleCount = Math.ceil(prefix / 4)
  const ptrParts = networkHex.slice(0, nibbleCount).split('').reverse().join('.')
  results.value = {
    '地址类型': ipv6Type(ip),
    '地址范围': ipv6Scope(ip),
    '压缩格式': compressIPv6(expanded),
    '展开格式': expanded,
    'IPv4 映射': ip.toLowerCase().includes('.') ? `是 → ${ip.slice(ip.lastIndexOf(':') + 1)}` : '否',
    'CIDR 前缀': `/${prefix}`,
    '网络地址': compressIPv6(bigIntToIPv6(networkBigInt)),
    '首可用 IP': compressIPv6(bigIntToIPv6(networkBigInt)),
    '末可用 IP': compressIPv6(bigIntToIPv6(lastAddr)),
    '主机位数': hostBits.toString(),
    '总 IP 数': totalHosts,
    'PTR 域名': `${ptrParts}.ip6.arpa`,
  }
}

// --- IPv6 特有功能 ---

/** 地址格式转换：任意写法 → 完整 / 压缩 / 十六进制 / 十进制 / 二进制 */
const calcFormat = () => {
  fmtResults.value = {}
  fmtBinaryRows.value = []
  fmtError.value = ''
  const val = fmtInput.value.trim()
  if (!val) return
  const expanded = parseIPv6(val)
  if (!expanded) { fmtError.value = '无效 IPv6'; return }
  const big = ipv6ToBigInt(expanded)
  const groups = expanded.split(':')
  fmtResults.value = {
    '完整格式': expanded,
    '压缩格式': compressIPv6(expanded),
    '十六进制': '0x' + big.toString(16).padStart(32, '0'),
    '十进制': big.toString(),
  }
  // 每行 16 位二进制，对应同行的十六进制分组
  fmtBinaryRows.value = groups.map((g, i) => ({
    index: i + 1,
    hex: g,
    binary: parseInt(g, 16).toString(2).padStart(16, '0'),
  }))
}

/** 前缀规划：给定前缀，计算可划分的 /48、/56、/64 数量并给出示例子网 */
const calcPlan = () => {
  planResults.value = {}
  planExamples.value = []
  planError.value = ''
  const val = planInput.value.trim()
  if (!val) return

  // 支持 "2001:db8::/32"，也支持只写 "/32"（此时以 2001:db8:: 作为示例基址）
  const matched = val.match(/^(.*?)\/(\d{1,3})$/)
  if (!matched) { planError.value = '格式: 地址/前缀 或 /前缀'; return }
  const prefix = parseInt(matched[2])
  if (isNaN(prefix) || prefix < 0 || prefix > 128) { planError.value = '前缀范围: 0-128'; return }

  const baseIp = matched[1].trim() || '2001:db8::'
  const expanded = parseIPv6(baseIp)
  if (!expanded) { planError.value = '无效 IPv6 地址'; return }

  const baseBig = ipv6ToBigInt(expanded)
  const maskBig = prefix === 0 ? 0n : ((1n << 128n) - (1n << BigInt(128 - prefix)))
  const networkBig = baseBig & maskBig

  planResults.value = {
    '输入前缀': `/${prefix}`,
    '可划分 /48': powCount(48 - prefix),
    '可划分 /56': powCount(56 - prefix),
    '可划分 /64': powCount(64 - prefix),
  }

  // 示例：优先用最常用的 /64；若输入前缀已细于 /64，则沿用输入前缀
  const samplePrefix = prefix <= 64 ? 64 : prefix
  planSamplePrefix.value = samplePrefix
  const blockSize = 1n << BigInt(128 - samplePrefix)
  for (let i = 0; i < 5; i++) {
    const subNet = networkBig + BigInt(i) * blockSize
    planExamples.value.push({
      cidr: `${compressIPv6(bigIntToIPv6(subNet))}/${samplePrefix}`,
      range: `${compressIPv6(bigIntToIPv6(subNet))} — ${compressIPv6(bigIntToIPv6(subNet + blockSize - 1n))}`,
    })
  }
}

/** 2 的 n 次方，过大时用 2^n 表示；n < 0 表示不可划分（返回空串走占位符） */
const powCount = (bits: number): string => {
  if (bits < 0) return ''
  if (bits === 0) return '1'
  if (bits <= 53) return (2 ** bits).toLocaleString()
  return `2^${bits}`
}

// --- 工具函数 ---
const ipv4ToNum = (ip: string): number | null => { const p = ip.split('.'); if (p.length !== 4) return null; let n = 0; for (const s of p) { const v = parseInt(s); if (isNaN(v) || v < 0 || v > 255) return null; n = (n << 8 | v) >>> 0 }; return n }
const numToIPv4 = (n: number): string => { return [(n >>> 24) & 0xff, (n >>> 16) & 0xff, (n >>> 8) & 0xff, n & 0xff].join('.') }
const numToBinary = (n: number): string => { return [(n >>> 24) & 0xff, (n >>> 16) & 0xff, (n >>> 8) & 0xff, n & 0xff].map(b => b.toString(2).padStart(8, '0')).join('.') }
const ipv4Type = (n: number): string => { const a = (n >>> 24) & 0xff, b = (n >>> 16) & 0xff; if (a === 127) return '环回地址'; if (a === 10) return 'A 类私有'; if (a === 172 && b >= 16 && b <= 31) return 'B 类私有'; if (a === 192 && b === 168) return 'C 类私有'; if (a === 169 && b === 254) return '链路本地'; if (a >= 224 && a <= 239) return '组播地址'; if (a >= 240) return '保留地址'; return '公网地址' }
const expandIPv6 = (ip: string): string | null => { try { let e = ip; if (e.includes('::')) { const p = e.split('::'); const l = p[0] ? p[0].split(':') : []; const r = p[1] ? p[1].split(':') : []; e = [...l, ...Array(8 - l.length - r.length).fill('0'), ...r].join(':') }; return e.split(':').map(g => g.padStart(4, '0')).join(':') } catch { return null } }
const compressIPv6 = (e: string): string => { const g = e.split(':').map(s => s.replace(/^0+/, '') || '0'); let bs = -1, bl = 0, cs = -1, cl = 0; for (let i = 0; i < 8; i++) { if (g[i] === '0') { if (cs === -1) cs = i; cl = i - cs + 1; if (cl > bl) { bs = cs; bl = cl } } else { cs = -1; cl = 0 } } if (bl >= 2) return g.slice(0, bs).join(':') + '::' + g.slice(bs + bl).join(':'); return g.join(':') }
const ipv6ToBigInt = (e: string): bigint => { let r = 0n; for (const g of e.split(':')) r = (r << 16n) | BigInt(parseInt(g, 16)); return r }
const bigIntToIPv6 = (n: bigint): string => { const g: string[] = []; for (let i = 7; i >= 0; i--) g.push(((n >> BigInt(i * 16)) & 0xffffn).toString(16).padStart(4, '0')); return g.join(':') }
const ipv6Type = (ip: string): string => { const l = ip.toLowerCase(); if (l.startsWith('::1')) return '环回地址'; if (l.startsWith('fe80')) return '链路本地'; if (l.startsWith('fc') || l.startsWith('fd')) return '唯一本地 (ULA)'; if (l.startsWith('ff')) return '组播地址'; if (l.startsWith('2001:db8')) return '文档地址'; if (l.includes('.')) return 'IPv4 映射'; return '全局单播' }
const ipv6Scope = (ip: string): string => { const l = ip.toLowerCase(); if (l === '::1') return '仅本机'; if (l.startsWith('fe80')) return '链路本地'; if (l.startsWith('fc') || l.startsWith('fd')) return '站点本地 (ULA)'; if (l.startsWith('ff02::1')) return '所有节点'; if (l.startsWith('ff02::2')) return '所有路由器'; if (l.startsWith('ff')) return '组播'; if (l.startsWith('2001:db8')) return '文档示例'; if (l.startsWith('2001:')) return '全球单播'; if (l.includes('.')) return 'IPv4 映射'; if (l.startsWith('64:ff9b')) return 'IPv4/IPv6 翻译'; if (l.startsWith('2002:')) return '6to4 隧道'; return '全球单播' }

/** 严格解析 IPv6（支持内嵌 IPv4 写法），返回 8 组 4 位十六进制的完整格式；非法返回 null */
const parseIPv6 = (ip: string): string | null => {
  let s = ip.trim().toLowerCase()
  // 基本语法校验：最多一个 "::"，且不允许 ":::"（否则 expandIPv6 会把非法写法静默修正掉）
  if (s.includes(':::') || s.split('::').length > 2) return null
  const v4 = s.match(/(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})$/)
  if (v4) {
    const n = ipv4ToNum(v4[1])
    if (n === null) return null
    s = s.slice(0, v4.index) + ((n >>> 16) & 0xffff).toString(16) + ':' + (n & 0xffff).toString(16)
  }
  const expanded = expandIPv6(s)
  if (!expanded || !/^[0-9a-f]{4}(:[0-9a-f]{4}){7}$/.test(expanded)) return null
  return expanded
}

onMounted(() => { calculate(); calcMask(); calcHosts(); calcFormat(); calcPlan() })
</script>

<template>
  <PageLayout title="子网计算器">
    <div class="calc-body">
      <!-- 版本切换 -->
      <div class="ver-switch">
        <el-segmented v-model="ipVer" :options="[{ label: 'IPv4', value: 'v4' }, { label: 'IPv6', value: 'v6' }]" @change="switchVer" />
      </div>

      <!-- CIDR 计算（左） + 右栏：IPv4 子网拆分 / IPv6 特有功能 -->
      <div class="section">
        <div class="split-layout">
          <div class="split-main">
            <div class="input-row">
              <el-input v-model="input" :placeholder="ipVer === 'v4' ? '10.0.0.0/24' : '2001:db8::/32'" style="width: 260px;" @keyup.enter="calculate" />
              <el-button type="primary" @click="calculate">计算</el-button>
              <el-alert v-if="error" type="error" :closable="false" class="row-alert">{{ error }}</el-alert>
            </div>
            <div class="result-grid">
              <template v-for="label in resultFields" :key="label">
                <div class="r-label">{{ label }}</div>
                <div class="r-value" :class="{ 'r-placeholder': !results[label] }">{{ results[label] || PLACEHOLDER }}</div>
              </template>
            </div>
          </div>

          <!-- IPv4：子网拆分 -->
          <div v-if="ipVer === 'v4'" class="split-side">
            <div class="input-row">
              <span class="row-label">拆分子网</span>
              <el-input-number v-model="splitCount" :min="2" :max="32" controls-position="right" placeholder="如 4" style="width: 110px;" />
              <el-button type="primary" @click="calculate">拆分</el-button>
            </div>
            <table class="split-table">
              <thead><tr><th>#</th><th>子网</th><th>范围</th><th>可用</th></tr></thead>
              <tbody>
                <tr v-if="!splits.length">
                  <td colspan="4" class="split-empty">暂无拆分结果，填写拆分数后点击「拆分」</td>
                </tr>
                <tr v-for="(s, i) in splits" :key="i">
                  <td>{{ i + 1 }}</td>
                  <td>{{ s.cidr }}</td>
                  <td>{{ s.range }}</td>
                  <td>{{ s.hosts || PLACEHOLDER }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- IPv6：地址格式转换 + 前缀规划 -->
          <div v-else class="split-side">
            <div class="input-row">
              <span class="row-label">地址格式</span>
              <el-input v-model="fmtInput" placeholder="2001:db8::1" style="width: 200px;" @keyup.enter="calcFormat" />
              <el-button @click="calcFormat">转换</el-button>
            </div>
            <el-alert v-if="fmtError" type="error" :closable="false" class="row-alert block-alert">{{ fmtError }}</el-alert>
            <div class="result-grid">
              <template v-for="label in IPV6_FMT_FIELDS" :key="'f' + label">
                <div class="r-label">{{ label }}</div>
                <div class="r-value" :class="{ 'r-placeholder': !fmtResults[label] }">{{ fmtResults[label] || PLACEHOLDER }}</div>
              </template>
            </div>
            <div class="sub-title">二进制分组（每行 16 位，共 8 行 / 128 位）</div>
            <table class="split-table">
              <thead><tr><th>#</th><th>十六进制</th><th>二进制</th></tr></thead>
              <tbody>
                <tr v-if="!fmtBinaryRows.length">
                  <td colspan="3" class="split-empty">暂无转换结果，填写地址后点击「转换」</td>
                </tr>
                <tr v-for="row in fmtBinaryRows" :key="row.index">
                  <td>{{ row.index }}</td>
                  <td>{{ row.hex }}</td>
                  <td class="bin">{{ row.binary }}</td>
                </tr>
              </tbody>
            </table>

            <div class="input-row divider">
              <span class="row-label">前缀规划</span>
              <el-input v-model="planInput" placeholder="2001:db8::/32" style="width: 200px;" @keyup.enter="calcPlan" />
              <el-button @click="calcPlan">规划</el-button>
            </div>
            <el-alert v-if="planError" type="error" :closable="false" class="row-alert block-alert">{{ planError }}</el-alert>
            <div class="result-grid">
              <template v-for="label in PLAN_FIELDS" :key="'p' + label">
                <div class="r-label">{{ label }}</div>
                <div class="r-value" :class="{ 'r-placeholder': !planResults[label] }">{{ planResults[label] || PLACEHOLDER }}</div>
              </template>
            </div>
            <div class="sub-title">示例 /{{ planSamplePrefix }} 子网</div>
            <table class="split-table">
              <thead><tr><th>#</th><th>子网</th><th>范围</th></tr></thead>
              <tbody>
                <tr v-if="!planExamples.length">
                  <td colspan="3" class="split-empty">暂无规划结果，填写前缀后点击「规划」</td>
                </tr>
                <tr v-for="(s, i) in planExamples" :key="i">
                  <td>{{ i + 1 }}</td>
                  <td>{{ s.cidr }}</td>
                  <td>{{ s.range }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- 掩码转换（仅 IPv4） -->
      <div v-if="ipVer === 'v4'" class="section section-narrow">
        <div class="input-row">
          <span class="row-label">掩码转换</span>
          <el-input v-model="maskInput" placeholder="/24 或 255.255.255.0" style="width: 260px;" @keyup.enter="calcMask" />
          <el-button @click="calcMask">转换</el-button>
          <el-alert v-if="maskError" type="error" :closable="false" class="row-alert">{{ maskError }}</el-alert>
        </div>
        <div class="result-grid">
          <template v-for="label in MASK_FIELDS" :key="'m' + label">
            <div class="r-label">{{ label }}</div>
            <div class="r-value" :class="{ 'r-placeholder': !maskResults[label] }">{{ maskResults[label] || PLACEHOLDER }}</div>
          </template>
        </div>
      </div>

      <!-- 主机数反算（仅 IPv4） -->
      <div v-if="ipVer === 'v4'" class="section section-narrow">
        <div class="input-row">
          <span class="row-label">主机数反算</span>
          <el-input-number v-model="hostCount" :min="1" controls-position="right" placeholder="如 100" style="width: 140px;" @keyup.enter="calcHosts" />
          <el-button @click="calcHosts">推荐</el-button>
          <el-alert v-if="hostError" type="error" :closable="false" class="row-alert">{{ hostError }}</el-alert>
        </div>
        <div class="result-grid">
          <template v-for="label in HOST_FIELDS" :key="'h' + label">
            <div class="r-label">{{ label }}</div>
            <div class="r-value" :class="{ 'r-placeholder': !hostResults[label] }">{{ hostResults[label] || PLACEHOLDER }}</div>
          </template>
        </div>
      </div>
    </div>
  </PageLayout>
</template>

<style scoped>
/* 整体向中间靠拢：左侧留白 20%，内容占据其余宽度 */
.calc-body { display: flex; flex-direction: column; gap: 20px; margin-left: 20%; max-width: 1400px; }
.ver-switch { margin-bottom: 0; }
.section { padding-bottom: 16px; border-bottom: 1px solid var(--el-border-color-lighter); }
.section:last-child { border-bottom: none; padding-bottom: 0; }
/* 掩码转换、主机数反算保持窄栏，避免在宽屏下过度拉伸 */
.section-narrow { max-width: 640px; }

/* CIDR 结果在左，拆分结果 / IPv6 工具在右 */
.split-layout { display: flex; gap: 28px; align-items: flex-start; }
.split-main { flex: 0 0 520px; min-width: 0; }
.split-side { flex: 1 1 auto; min-width: 0; }

.input-row { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; }
.input-row.divider { margin-top: 16px; padding-top: 14px; border-top: 1px dashed var(--el-border-color-lighter); }
.row-label { font-size: 13px; font-weight: 600; color: var(--el-text-color-secondary); white-space: nowrap; }
/* 错误提示紧跟在按钮右侧，不另起一行挤占下方内容 */
.row-alert { flex: 1 1 auto; min-width: 0; padding: 2px 10px; }
.row-alert :deep(.el-alert__content) { padding: 0; }
.row-alert :deep(.el-alert__title) { font-size: 12px; line-height: 1.5; }
/* 独处一行的错误提示（IPv6 工具区放不下时使用），同样贴近上方输入行 */
.block-alert { margin-bottom: 8px; }

.result-grid { display: grid; grid-template-columns: 90px 1fr; gap: 4px 12px; margin-bottom: 0; }
.r-label { font-size: 13px; color: var(--el-text-color-secondary); font-family: monospace; }
.r-value { font-size: 13px; font-weight: 600; font-family: monospace; word-break: break-all; }
.r-placeholder { color: var(--el-text-color-placeholder); font-weight: 400; }
.sub-title { font-size: 12px; font-weight: 600; color: var(--el-text-color-secondary); margin: 14px 0 4px; }

.split-table { width: 100%; border-collapse: collapse; font-size: 12px; font-family: monospace; }
.split-table th, .split-table td { padding: 4px 8px; border-bottom: 1px solid var(--el-border-color-lighter); text-align: left; }
.split-table th { font-weight: 600; color: var(--el-text-color-secondary); font-size: 11px; }
.split-empty { color: var(--el-text-color-placeholder); text-align: center; padding: 12px 0; }
.bin { letter-spacing: 1px; }

/* 窄屏回退：取消左缩进并改为上下排列 */
@media (max-width: 1280px) {
  .calc-body { margin-left: 0; }
  .split-layout { flex-direction: column; gap: 16px; }
  .split-main { flex: 1 1 auto; width: 100%; }
  .split-side { width: 100%; }
}
</style>
