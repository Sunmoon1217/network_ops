<script setup lang="ts">
import PageLayout from '@/ui/PageLayout.vue'
import { fetchAllPages } from '@/utils/fetchAllPages'
import { ElTooltip } from 'element-plus'

const loading = ref(false)
const cabinets = ref<any[]>([])
const devices = ref<any[]>([])
const selectedDC = ref<string | null>(null)
const selectedRoom = ref<string | null>(null)
const selectedRow = ref<string | null>(null)

const typeColorMap: Record<string, string> = {
  firewall: '#ef4444', switch: '#3b82f6', router: '#10b981',
  loadbalancer: '#f59e0b', server: '#8b5cf6', dns: '#6366f1',
}
const getDeviceColor = (d: any) => typeColorMap[d.device_type] || '#6b7280'

const dcOptions = computed(() => {
  const set = new Set(cabinets.value.map(c => c.datacenter_name).filter(Boolean))
  return Array.from(set).map(d => ({ label: d, value: d }))
})
const roomOptions = computed(() => {
  const set = new Set(cabinets.value.filter(c => c.datacenter_name === selectedDC.value).map(c => c.room_name).filter(Boolean))
  return Array.from(set).map(r => ({ label: r, value: r }))
})
const rowOptions = computed(() => {
  const rows = new Map<string, string>()
  cabinets.value.forEach(c => {
    if (c.row && c.datacenter_name === selectedDC.value && c.room_name === selectedRoom.value) rows.set(c.row, c.row)
  })
  return Array.from(rows.values()).sort().map(r => ({ label: `${r} 排`, value: r }))
})

const rowCabinets = computed(() => {
  if (!selectedRow.value) return []
  return cabinets.value
    .filter(c => c.datacenter_name === selectedDC.value && c.room_name === selectedRoom.value && c.row === selectedRow.value)
    .sort((a, b) => a.name.localeCompare(b.name))
})
const rowDevices = computed(() => {
  const ids = new Set(rowCabinets.value.map(c => c.id))
  return devices.value.filter(d => d.cabinet && ids.has(d.cabinet))
})
const devicesByCabinet = computed(() => {
  const map = new Map<number, any[]>()
  rowDevices.value.forEach(d => {
    const cid = typeof d.cabinet === 'object' ? d.cabinet.id : d.cabinet
    const list = map.get(cid) || []
    list.push(d)
    map.set(cid, list)
  })
  return map
})
const totalU = computed(() => rowCabinets.value.reduce((s, c) => s + (c.total_u || 42), 0))
const usedU = computed(() => rowDevices.value.reduce((s, d) => s + (d.height || 1), 0))
const utilization = computed(() => totalU.value ? Math.round(usedU.value / totalU.value * 100) : 0)

onMounted(async () => {
  loading.value = true
  try {
    // 页面需在前端做设备分组、U 位利用率统计并生成三级下拉选项，
    // 分页会静默截断数据，故必须循环拉取全量（page_size=1000 会被后端上限截断为 500 且仅返回第一页）
    const [allCabinets, allDevices] = await Promise.all([
      fetchAllPages('/api/assets/cabinets/', { ordering: 'name' }),
      fetchAllPages('/api/assets/devices/', { ordering: 'hostname' }),
    ])
    cabinets.value = allCabinets
    devices.value = allDevices
  } finally { loading.value = false }
})
</script>

<template>
  <PageLayout title="机柜视图">
    <template #actions>
      <el-select v-model="selectedDC" placeholder="数据中心" clearable style="width: 160px">
        <el-option v-for="o in dcOptions" :key="o.value" :label="o.label" :value="o.value" />
      </el-select>
      <el-select v-model="selectedRoom" placeholder="机房" clearable style="width: 160px">
        <el-option v-for="o in roomOptions" :key="o.value" :label="o.label" :value="o.value" />
      </el-select>
      <el-select v-model="selectedRow" placeholder="排" clearable style="width: 120px">
        <el-option v-for="o in rowOptions" :key="o.value" :label="o.label" :value="o.value" />
      </el-select>
      <template v-if="selectedRow">
        <el-tag>机柜 {{ rowCabinets.length }}</el-tag>
        <el-tag>设备 {{ rowDevices.length }}</el-tag>
        <el-tag>U位 {{ usedU }}/{{ totalU }} ({{ utilization }}%)</el-tag>
      </template>
    </template>

    <div v-loading="loading" class="rack-container">
      <el-empty v-if="!selectedRow" description="请选择数据中心 → 机房 → 排" />
      <el-empty v-else-if="rowCabinets.length === 0" description="该排暂无机柜" />
      <div v-else class="rack-row-scroll">
        <div v-for="cabinet in rowCabinets" :key="cabinet.id" class="rack-unit">
          <div class="rack-title">
            <strong>{{ cabinet.name }}</strong>
            <el-tag :type="cabinet.status === 'active' ? 'success' : 'info'" size="small" effect="dark">{{ cabinet.total_u }}U</el-tag>
          </div>
          <div class="rack-frame">
            <div v-for="u in Array.from({ length: cabinet.total_u || 42 }, (_, i) => (cabinet.total_u || 42) - i)" :key="u" class="rack-row">
              <span class="u-num">{{ u }}</span>
              <div class="u-cell">
                <template v-for="d in devicesByCabinet.get(cabinet.id) || []" :key="d.id">
                  <el-tooltip v-if="d.u_position + d.height - 1 === u" placement="right">
                    <div class="device-block" :style="{ backgroundColor: getDeviceColor(d), height: (d.height || 1) * 26 - 2 + 'px' }">
                      <span class="device-label">{{ d.hostname }}</span>
                    </div>
                    <template #content>
                      <div><strong>{{ d.hostname }}</strong></div>
                      <div>IP: {{ d.ip_address || '未分配' }}</div>
                      <div>类型: {{ d.device_type_display || d.device_type }}</div>
                      <div>U位: {{ d.u_position }} ({{ d.height || 1 }}U)</div>
                    </template>
                  </el-tooltip>
                </template>
              </div>
              <span class="u-num">{{ u }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </PageLayout>
</template>

<style scoped>
.rack-container { flex: 1; min-height: 0; overflow: auto; }
.rack-row-scroll { display: flex; gap: 16px; align-items: flex-start; overflow-x: auto; padding-bottom: 12px; }
.rack-unit { flex-shrink: 0; }
.rack-title { display: flex; align-items: center; justify-content: center; gap: 8px; margin-bottom: 6px; font-size: 13px; }
.rack-frame { border: 2px solid var(--el-border-color); border-radius: 4px; background: var(--el-fill-color-darker, #1f2937); padding: 2px; width: 220px; }
.rack-row { display: flex; height: 26px; align-items: center; border-bottom: 1px solid var(--el-border-color); }
.rack-row:last-child { border-bottom: none; }
.u-num { width: 26px; text-align: center; font-size: 10px; color: var(--el-text-color-secondary); font-family: monospace; flex-shrink: 0; }
.u-cell { flex: 1; height: 100%; position: relative; }
.device-block { position: absolute; top: 1px; left: 0; right: 0; border-radius: 2px; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: opacity 0.2s; overflow: hidden; z-index: 1; }
.device-block:hover { opacity: 0.85; }
.device-label { font-size: 10px; font-weight: 600; color: white; text-shadow: 0 1px 2px rgba(0,0,0,0.3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; padding: 0 2px; }
</style>
