<script setup lang="ts">
import PageLayout from '@/ui/PageLayout.vue'

const ipVer = ref<'v4' | 'v6'>('v4')
const input = ref('10.0.0.0/24')
const splitCount = ref<number | null>(null)
const hostCount = ref<number | null>(null)
const maskInput = ref('')
const results = ref<any[]>([])
const splits = ref<any[]>([])
const maskResults = ref<any[]>([])
const hostResults = ref<any[]>([])
const error = ref('')



function switchVer() {
  input.value = ipVer.value === 'v4' ? '10.0.0.0/24' : '2001:db8::/32'
  results.value = []; splits.value = []; maskResults.value = []; hostResults.value = []; error.value = ''
  splitCount.value = null; hostCount.value = null; maskInput.value = ''
}

function calculate() {
  error.value = ''; results.value = []; splits.value = []
  try { ipVer.value === 'v6' ? calcIPv6() : calcIPv4() } catch (e: any) { error.value = e.message || '计算错误' }
}

function calcMask() {
  maskResults.value = []
  const val = maskInput.value.trim()
  if (!val) return
  if (val.startsWith('/')) {
    const prefix = parseInt(val.slice(1))
    if (isNaN(prefix) || prefix < 0 || prefix > 32) return
    const mask = prefix === 0 ? 0 : (~0 << (32 - prefix)) >>> 0
    maskResults.value.push(
      { label: 'CIDR', value: `/${prefix}` },
      { label: '点分十进制', value: numToIPv4(mask) },
      { label: '十六进制', value: '0x' + (mask >>> 0).toString(16).toUpperCase().padStart(8, '0') },
      { label: '二进制', value: numToBinary(mask) },
      { label: '可用主机数', value: (prefix >= 31 ? Math.pow(2, 32 - prefix) : Math.pow(2, 32 - prefix) - 2).toLocaleString() },
    )
  } else {
    const num = ipv4ToNum(val)
    if (num === null) return
    const binary = num.toString(2).padStart(32, '0')
    if (!/^1*0*$/.test(binary)) { maskResults.value.push({ label: '错误', value: '不是合法子网掩码' }); return }
    const prefix = binary.indexOf('0') === -1 ? 32 : binary.indexOf('0')
    maskResults.value.push(
      { label: '点分十进制', value: val },
      { label: 'CIDR', value: `/${prefix}` },
      { label: '十六进制', value: '0x' + (num >>> 0).toString(16).toUpperCase().padStart(8, '0') },
      { label: '二进制', value: numToBinary(num) },
      { label: '通配符掩码', value: numToIPv4((~num) >>> 0) },
      { label: '可用主机数', value: (prefix >= 31 ? Math.pow(2, 32 - prefix) : Math.pow(2, 32 - prefix) - 2).toLocaleString() },
    )
  }
}

function calcHosts() {
  hostResults.value = []
  if (!hostCount.value || hostCount.value < 1) return
  const needed = hostCount.value + 2
  const bits = Math.ceil(Math.log2(needed))
  const prefix = 32 - bits
  if (prefix < 0) { hostResults.value.push({ label: '错误', value: '超出范围' }); return }
  const mask = prefix === 0 ? 0 : (~0 << (32 - prefix)) >>> 0
  hostResults.value.push(
    { label: '推荐 CIDR', value: `/${prefix}` },
    { label: '子网掩码', value: numToIPv4(mask) },
    { label: '实际可用', value: (Math.pow(2, bits) - 2).toLocaleString() },
  )
}

function calcIPv4() {
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
  results.value.push(
    { label: '地址类型', value: ipv4Type(ipNum) },
    { label: '网络地址', value: numToIPv4(network) },
    { label: '广播地址', value: numToIPv4(broadcast) },
    { label: '子网掩码', value: `${numToIPv4(mask)}  /${prefix}` },
    { label: '通配符掩码', value: numToIPv4(wildcard) },
    { label: '十六进制', value: '0x' + (mask >>> 0).toString(16).toUpperCase().padStart(8, '0') },
    { label: '总 IP', value: total.toLocaleString() },
    { label: '可用 IP', value: usable.toLocaleString() },
    { label: '首可用', value: total >= 2 ? numToIPv4(network + 1) : '-' },
    { label: '末可用', value: total >= 2 ? numToIPv4(broadcast - 1) : '-' },
    { label: '二进制掩码', value: numToBinary(mask) },
  )
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

function calcIPv6() {
  const parts = input.value.trim().split('/')
  if (parts.length !== 2) { error.value = '格式: IPv6/CIDR'; return }
  const ip = parts[0]
  const prefix = parseInt(parts[1])
  if (isNaN(prefix) || prefix < 0 || prefix > 128) { error.value = 'CIDR 范围: 0-128'; return }
  const expanded = expandIPv6(ip)
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
  results.value.push(
    { label: '地址类型', value: ipv6Type(ip) },
    { label: '地址范围', value: ipv6Scope(ip) },
    { label: '压缩格式', value: compressIPv6(expanded) },
    { label: '展开格式', value: expanded },
    { label: 'IPv4 映射', value: ip.toLowerCase().startsWith('::ffff:') ? `是 → ${ip.slice(7)}` : '否' },
    { label: 'CIDR 前缀', value: `/${prefix}` },
    { label: '网络地址', value: compressIPv6(bigIntToIPv6(networkBigInt)) },
    { label: '首可用 IP', value: compressIPv6(bigIntToIPv6(networkBigInt)) },
    { label: '末可用 IP', value: compressIPv6(bigIntToIPv6(lastAddr)) },
    { label: '主机位数', value: hostBits.toString() },
    { label: '总 IP 数', value: totalHosts },
    { label: 'PTR 域名', value: `${ptrParts}.ip6.arpa` },
  )
  if (splitCount.value && splitCount.value > 1 && prefix < 64) {
    const newPrefix = prefix + Math.ceil(Math.log2(splitCount.value))
    if (newPrefix > 64) { error.value = 'IPv6 拆分建议不超过 /64'; return }
    const blockSize = 1n << BigInt(128 - newPrefix)
    for (let i = 0; i < Math.min(splitCount.value, 16); i++) {
      const subNet = networkBigInt + BigInt(i) * blockSize
      splits.value.push({ cidr: `${compressIPv6(bigIntToIPv6(subNet))}/${newPrefix}`, range: `${compressIPv6(bigIntToIPv6(subNet))} — ${compressIPv6(bigIntToIPv6(subNet + blockSize - 1n))}`, hosts: '' })
    }
  }
}

// --- 工具函数 ---
function ipv4ToNum(ip: string): number | null { const p = ip.split('.'); if (p.length !== 4) return null; let n = 0; for (const s of p) { const v = parseInt(s); if (isNaN(v) || v < 0 || v > 255) return null; n = (n << 8 | v) >>> 0 }; return n }
function numToIPv4(n: number): string { return [(n >>> 24) & 0xff, (n >>> 16) & 0xff, (n >>> 8) & 0xff, n & 0xff].join('.') }
function numToBinary(n: number): string { return [(n >>> 24) & 0xff, (n >>> 16) & 0xff, (n >>> 8) & 0xff, n & 0xff].map(b => b.toString(2).padStart(8, '0')).join('.') }
function ipv4Type(n: number): string { const a = (n >>> 24) & 0xff, b = (n >>> 16) & 0xff; if (a === 127) return '环回地址'; if (a === 10) return 'A 类私有'; if (a === 172 && b >= 16 && b <= 31) return 'B 类私有'; if (a === 192 && b === 168) return 'C 类私有'; if (a === 169 && b === 254) return '链路本地'; if (a >= 224 && a <= 239) return '组播地址'; if (a >= 240) return '保留地址'; return '公网地址' }
function expandIPv6(ip: string): string | null { try { let e = ip; if (e.includes('::')) { const p = e.split('::'); const l = p[0] ? p[0].split(':') : []; const r = p[1] ? p[1].split(':') : []; e = [...l, ...Array(8 - l.length - r.length).fill('0'), ...r].join(':') }; return e.split(':').map(g => g.padStart(4, '0')).join(':') } catch { return null } }
function compressIPv6(e: string): string { const g = e.split(':').map(s => s.replace(/^0+/, '') || '0'); let bs = -1, bl = 0, cs = -1, cl = 0; for (let i = 0; i < 8; i++) { if (g[i] === '0') { if (cs === -1) cs = i; cl = i - cs + 1; if (cl > bl) { bs = cs; bl = cl } } else { cs = -1; cl = 0 } } if (bl >= 2) return g.slice(0, bs).join(':') + '::' + g.slice(bs + bl).join(':'); return g.join(':') }
function ipv6ToBigInt(e: string): bigint { let r = 0n; for (const g of e.split(':')) r = (r << 16n) | BigInt(parseInt(g, 16)); return r }
function bigIntToIPv6(n: bigint): string { const g: string[] = []; for (let i = 7; i >= 0; i--) g.push(((n >> BigInt(i * 16)) & 0xffffn).toString(16).padStart(4, '0')); return g.join(':') }
function ipv6Type(ip: string): string { const l = ip.toLowerCase(); if (l.startsWith('::1')) return '环回地址'; if (l.startsWith('fe80')) return '链路本地'; if (l.startsWith('fc') || l.startsWith('fd')) return '唯一本地 (ULA)'; if (l.startsWith('ff')) return '组播地址'; if (l.startsWith('2001:db8')) return '文档地址'; if (l.startsWith('::ffff:')) return 'IPv4 映射'; return '全局单播' }
function ipv6Scope(ip: string): string { const l = ip.toLowerCase(); if (l === '::1') return '仅本机'; if (l.startsWith('fe80')) return '链路本地'; if (l.startsWith('fc') || l.startsWith('fd')) return '站点本地 (ULA)'; if (l.startsWith('ff02::1')) return '所有节点'; if (l.startsWith('ff02::2')) return '所有路由器'; if (l.startsWith('ff')) return '组播'; if (l.startsWith('2001:db8')) return '文档示例'; if (l.startsWith('2001:')) return '全球单播'; if (l.startsWith('::ffff:')) return 'IPv4 映射'; if (l.startsWith('64:ff9b')) return 'IPv4/IPv6 翻译'; if (l.startsWith('2002:')) return '6to4 隧道'; return '全球单播' }

onMounted(() => { calculate(); calcMask(); calcHosts() })
</script>

<template>
  <PageLayout title="子网计算器">
    <div class="calc-body">
      <!-- 版本切换 -->
      <div class="ver-switch">
        <el-segmented v-model="ipVer" :options="[{ label: 'IPv4', value: 'v4' }, { label: 'IPv6', value: 'v6' }]" @change="switchVer" />
      </div>

      <!-- CIDR 计算 + 结果 -->
      <div class="section">
        <div class="input-row">
          <el-input v-model="input" :placeholder="ipVer === 'v4' ? '10.0.0.0/24' : '2001:db8::/32'" style="width: 260px;" @keyup.enter="calculate" />
          <el-button type="primary" @click="calculate">计算</el-button>
        </div>
        <el-alert v-if="error" type="error" :closable="false" style="margin-top: 8px;">{{ error }}</el-alert>
        <div v-if="results.length" class="result-grid">
          <template v-for="(item, idx) in results" :key="idx">
            <div class="r-label">{{ item.label }}</div>
            <div class="r-value">{{ item.value }}</div>
          </template>
        </div>
          <thead><tr><th>#</th><th>子网</th><th>范围</th><th>可用</th></tr></thead>
          <tbody><tr v-for="(s, i) in splits" :key="i"><td>{{ i + 1 }}</td><td>{{ s.cidr }}</td><td>{{ s.range }}</td><td>{{ s.hosts }}</td></tr></tbody>
        <div class="input-row">
          <span class="row-label">拆分子网</span>
          <el-input-number v-model="splitCount" :min="2" :max="32" controls-position="right" style="width: 100px;" />
          <el-button type="primary" @click="calculate">拆分</el-button>
        </div>
        <table class="split-table">
          <thead><tr><th>#</th><th>子网</th><th>范围</th><th>可用</th></tr></thead>
          <tbody><tr v-for="(s, i) in splits" :key="i"><td>{{ i + 1 }}</td><td>{{ s.cidr }}</td><td>{{ s.range }}</td><td>{{ s.hosts }}</td></tr></tbody>
        </table>
      </div>

      <!-- 掩码转换（仅 IPv4） -->
      <div v-if="ipVer === 'v4'" class="section">
        <div class="input-row">
          <span class="row-label">掩码转换</span>
          <el-input v-model="maskInput" placeholder="/24 或 255.255.255.0" style="width: 260px;" @keyup.enter="calcMask" />
          <el-button @click="calcMask">转换</el-button>
        </div>
        <div v-if="maskResults.length" class="result-grid">
          <template v-for="(item, idx) in maskResults" :key="'m'+idx">
            <div class="r-label">{{ item.label }}</div>
            <div class="r-value">{{ item.value }}</div>
          </template>
        </div>
      </div>

      <!-- 主机数反算（仅 IPv4） -->
      <div v-if="ipVer === 'v4'" class="section">
        <div class="input-row">
          <span class="row-label">主机数反算</span>
          <el-input-number v-model="hostCount" :min="1" controls-position="right" style="width: 140px;" @keyup.enter="calcHosts" />
          <el-button @click="calcHosts">推荐</el-button>
        </div>
        <div v-if="hostResults.length" class="result-grid">
          <template v-for="(item, idx) in hostResults" :key="'h'+idx">
            <div class="r-label">{{ item.label }}</div>
            <div class="r-value">{{ item.value }}</div>
          </template>
        </div>
      </div>
    </div>
  </PageLayout>
</template>

<style scoped>
.calc-body { max-width: 640px; }
.ver-switch { margin-bottom: 20px; }
.section { margin-bottom: 20px; padding-bottom: 16px; border-bottom: 1px solid var(--el-border-color-lighter); }
.section:last-child { border-bottom: none; }
.input-row { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; }
.sep { color: var(--el-border-color); font-size: 18px; }
.row-label { font-size: 13px; font-weight: 600; color: var(--el-text-color-secondary); white-space: nowrap; }
.result-grid { display: grid; grid-template-columns: 90px 1fr; gap: 4px 12px; margin-bottom: 10px; }
.r-label { font-size: 13px; color: var(--el-text-color-secondary); font-family: monospace; }
.r-value { font-size: 13px; font-weight: 600; font-family: monospace; word-break: break-all; }
.split-table { width: 100%; border-collapse: collapse; font-size: 12px; font-family: monospace; margin-top: 8px; }
.split-table th, .split-table td { padding: 4px 8px; border-bottom: 1px solid var(--el-border-color-lighter); text-align: left; }
.split-table th { font-weight: 600; color: var(--el-text-color-secondary); font-size: 11px; }
</style>
