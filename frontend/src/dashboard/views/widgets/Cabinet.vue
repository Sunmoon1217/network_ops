<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { getDashboardCabinets } from '@/api/dashboard'
import type { DashboardCabinet, DashboardCabinetDevice } from '@dashboard/types'
import { useInterval } from '@dashboard/utils/timer'

const cabinets = ref<DashboardCabinet[]>([])
const devices = ref<DashboardCabinetDevice[]>([])
const selectedDC = ref('')
const selectedCabinet = ref<number | null>(null)
const hoverDevice = ref<DashboardCabinetDevice | null>(null)
const loadError = ref('')

const dcOptions = computed(() =>
  Array.from(new Set(cabinets.value.map((c) => c.datacenter_name).filter(Boolean))),
)
const cabinetOptions = computed(() =>
  cabinets.value.filter((c) => !selectedDC.value || c.datacenter_name === selectedDC.value),
)
const current = computed(() => cabinets.value.find((c) => c.id === selectedCabinet.value) ?? null)
const uCount = computed(() => current.value?.total_u || 42)
const cabinetDevices = computed(() =>
  devices.value.filter((d) => d.cabinet === selectedCabinet.value && d.u_position),
)
const usedU = computed(() => cabinetDevices.value.reduce((sum, d) => sum + (d.height || 1), 0))
const utilization = computed(() =>
  uCount.value ? Math.round((usedU.value / uCount.value) * 100) : 0,
)
const uRows = computed(() => Array.from({ length: uCount.value }, (_, i) => uCount.value - i))
const rackStyle = computed(() => ({ gridTemplateRows: `repeat(${uCount.value}, 16px)` }))

const deviceStyle = (device: DashboardCabinetDevice) => {
  const height = device.height || 1
  const start = uCount.value - Number(device.u_position) - height + 2
  return {
    gridColumn: '2',
    gridRow: `${Math.max(1, start)} / span ${height}`,
  }
}

const loadCabinets = async () => {
  try {
    const previous = selectedCabinet.value
    // 大屏专用只读接口（免认证）：一次返回机柜与设备上架位置，不需要登录态
    const data = await getDashboardCabinets()
    cabinets.value = data.cabinets
    devices.value = data.devices
    if (!selectedDC.value) selectedDC.value = dcOptions.value[0] ?? ''
    if (!cabinets.value.some((c) => c.id === previous)) {
      selectedCabinet.value = cabinetOptions.value[0]?.id ?? null
    }
    loadError.value = ''
  } catch (error) {
    console.error('[dashboard] 机柜数据获取失败:', error)
    loadError.value = '机柜数据获取失败'
  }
}

watch(selectedDC, () => {
  if (!cabinetOptions.value.some((c) => c.id === selectedCabinet.value)) {
    selectedCabinet.value = cabinetOptions.value[0]?.id ?? null
  }
})

const { start } = useInterval(loadCabinets, 5 * 60 * 1000, true)

onMounted(() => {
  start()
})
</script>

<template>
  <div class="container">
    <div v-if="loadError" class="empty-state">{{ loadError }}</div>
    <div v-else-if="!cabinets.length" class="empty-state">资产库暂无机柜数据</div>
    <template v-else>
      <div class="rack-wrap">
        <div class="select">
          <select v-model="selectedDC" aria-label="数据中心">
            <option value="">全部数据中心</option>
            <option v-for="dc in dcOptions" :key="dc" :value="dc">{{ dc }}</option>
          </select>
          <select v-model.number="selectedCabinet" aria-label="机柜">
            <option v-for="cabinet in cabinetOptions" :key="cabinet.id" :value="cabinet.id">
              {{ cabinet.name }}
            </option>
          </select>
        </div>
        <div class="usage">
          机柜 {{ current?.name || '--' }} · {{ uCount }}U · 已用 {{ usedU }}U · 利用率 {{ utilization }}%
        </div>
        <div v-if="current" class="rack" :style="rackStyle">
          <div
            v-for="u in uRows"
            :key="`label-${u}`"
            class="u-label"
            :style="{ gridRow: uCount - u + 1, gridColumn: 1 }"
          >{{ u }}</div>
          <div
            v-for="u in uRows"
            :key="`cell-${u}`"
            class="u-cell"
            :style="{ gridRow: uCount - u + 1, gridColumn: 2 }"
          ></div>
          <div
            v-for="device in cabinetDevices"
            :key="device.id"
            class="device"
            :style="deviceStyle(device)"
            :title="`${device.hostname} · ${device.u_position}U · ${device.height || 1}U`"
            @mouseenter="hoverDevice = device"
          >{{ device.hostname }}</div>
        </div>
        <div v-else class="empty-state">请选择机柜</div>
      </div>
      <div class="detail">
        <h4>设备信息</h4>
        <template v-if="hoverDevice">
          <p>名称：{{ hoverDevice.hostname }}</p>
          <p>IP：{{ hoverDevice.ip_address || '未分配' }}</p>
          <p>类型：{{ hoverDevice.device_type_display || '未设置' }}</p>
          <p>U 位：{{ hoverDevice.u_position }}（{{ hoverDevice.height || 1 }}U）</p>
        </template>
        <p v-else class="hint">鼠标移到机柜设备上查看详情</p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.container { height: 100%; display: grid; grid-template-columns: 1.4fr 1fr; gap: 8px; overflow: hidden; }
.empty-state { padding: 12px; font-size: 12px; color: #88a9c8; }

.rack-wrap { min-height: 0; overflow: auto; display: flex; flex-direction: column; gap: 6px; }
.rack-wrap::-webkit-scrollbar { width: 0; }

.select { display: flex; gap: 6px; }
.select select {
  flex: 1;
  min-width: 0;
  padding: 4px 6px;
  border-radius: 8px;
  border: 1px solid rgba(111, 244, 255, 0.25);
  background: #10263b;
  color: #d7ecfb;
  font-size: 11px;
}

.usage { font-size: 11px; color: #9fd7ff; }

.rack {
  display: grid;
  grid-template-columns: 26px 1fr;
  gap: 1px;
  padding: 2px;
  border: 1px solid #455f87;
  border-radius: 4px;
  background: rgba(10, 20, 40, 0.6);
}

.u-label {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 9px;
  color: #40c0ff;
  background: rgba(47, 47, 106, 0.5);
}

.u-cell {
  border: 1px solid rgba(111, 244, 255, 0.08);
  background: rgba(20, 20, 40, 0.3);
}

.device {
  z-index: 1;
  display: flex;
  align-items: center;
  padding: 0 6px;
  border: 1px solid #60ffcc;
  border-radius: 3px;
  background: rgba(10, 20, 40, 0.92);
  color: #a0ffdd;
  font-size: 10px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.detail {
  border: 1px solid rgba(111, 244, 255, 0.14);
  border-radius: 12px;
  padding: 10px;
  font-size: 12px;
  color: #d7ecfb;
  overflow: hidden;
}

.detail h4 { margin: 0 0 8px; font-size: 13px; color: #ecf7ff; }
.detail p { margin: 6px 0; word-break: break-all; }
.detail .hint { color: #88a9c8; }
</style>
