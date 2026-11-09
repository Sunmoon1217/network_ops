<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { getidc, getrack, getracklist } from '@/api/dashboard_api'
import type { DeviceInfo, PositionInfo, RackInfo } from '@/types'
import type { SelectProps, TooltipProps } from 'naive-ui'
import axios from 'axios'

interface Option {
  label: string
  value: string
}
const uCount = ref(45) // 常见机柜高度

const deviceData = ref<PositionInfo[]>([])
const options = ref<Option[]>([])
const idclist = ref<Option[]>([])
const rowlist = ref<Option[]>([])
const racklist = ref<Option[]>([])
const curr_idc = ref('')
const curr_rack = ref<RackInfo>({ name: '', uCount: 0, detail: deviceData.value })
const curr_device = ref<DeviceInfo | null>(null)

const fetch_idc = async () => {
  const response = await getidc()
  console.log('API返回option信息:', response)
  idclist.value = response.map((item: string) => ({ label: item, value: item }))
  curr_idc.value = idclist.value[0].value
}

const fetch_racklist = async (idc?: string) => {
  const response = await getracklist(idc)
  console.log('API返回option信息:', response)
  racklist.value = response.map((item: string) => ({ label: item, value: item }))
}

const fetch_rack = async (idc: string, rack_id: string) => {
  const response = await getrack(idc, rack_id)
  console.log('API返回rack信息:', response)
  curr_rack.value = response[0]
  uCount.value = curr_rack.value.uCount
  console.log('uCount:', uCount.value)
}

const handleIDC = (value: string) => {
  console.log('选择机房:', value)
  curr_idc.value = value
  fetch_racklist(curr_idc.value)
}

const handleSelect = (value: string) => {
  console.log('选择机柜:', value)
  fetch_rack(curr_idc.value, value)
}

const rackRepeat = computed(() => ({
  gridTemplateRows: `repeat(${uCount.value}, 16px)`,
}))

type SelectThemeOverrides = NonNullable<SelectProps['themeOverrides']>
const selectOverrides: SelectThemeOverrides = {
  peers: {
    InternalSelection: {
      color: '#263740', // 背景颜色
      textColor: 'var(--text-color)', // 字体颜色
      colorActive: '#263740', // 点开后背景颜色
      // placeholderColor: '#ff0', // 占位符字体颜色
    },
    InternalSelectMenu: {
      color: '#203040', // 展开背景色
      // actionTextColor: '#000', // 展开字体颜色
      optionColorActive: 'var(--text-color)', // 展开活动选项背景色
      optionTextColor: '#60f0ff', //
      // optionTextColorActive: '#6688aa',
      optionColorPending: '#305060', // 选项 hover 背景
      optionColorActivePending: '#101010',
      optionTextColorPressed: '#101010',
    },
  },
}

onMounted(async () => {
  await fetch_idc()
  await fetch_racklist(curr_idc.value)
  await fetch_rack(curr_idc.value, racklist.value[0].value)
})
</script>

<template>
  <div class="container">
    <div class="rackcontainer">
      <div class="rack">
        <!-- 左侧：U 位刻度（偶数） -->
        <div class="rackpositionl" :style="rackRepeat">
          <template v-for="n in uCount" :key="n">
            <div
              v-if="n % 2 === 0"
              :class="['cell cellrepeat', n === uCount ? 'last-cell' : '']"
              :style="{ '--row-height': -n - 1 }"
            >
              <p class="side">{{ n }}U</p>
            </div>
          </template>
        </div>

        <!-- 中间：设备区域 -->
        <div class="rackmain" :style="rackRepeat">
          <template v-for="(position, index) of curr_rack.detail" :key="index">
            <template v-if="position.device.name !== ''">
              <div
                class="cell celldevice"
                @mouseenter="curr_device = position.device"
                :style="{
                  '--row-start': -Number(position.position),
                  '--row-end': -Number(position.position) - position.device.height,
                }"
              >
                <div class="device-label">
                  <n-ellipsis style="max-width: 120px">
                    {{ position.device.name }}
                  </n-ellipsis>
                  <!-- <span class="height-badge">{{ device.device.height }}U</span> -->
                </div>
              </div>
            </template>
            <template v-else>
              <div class="cell cellempty" :style="{ '--row-start': -position.position - 1 }">
                {{ position.position }}U
              </div>
            </template>
          </template>
        </div>

        <!-- 右侧：U 位刻度（奇数） -->
        <div class="rackpositionr" :style="rackRepeat">
          <template v-for="n in uCount" :key="n">
            <div
              v-if="n % 2 === 1"
              :class="['cell cellrepeat', n === uCount ? 'last-cell' : '']"
              :style="{ '--row-height': -n - 1 }"
            >
              <p class="side">{{ n }}U</p>
            </div>
          </template>
        </div>
      </div>
    </div>
    <div class="displaycontainer">
      <div class="select">
        <n-select
          filterable
          :options="idclist"
          placeholder="请选择机房"
          @update:value="handleIDC"
          :theme-overrides="selectOverrides"
        />
        <n-select
          filterable
          :options="racklist"
          placeholder="请选择机柜"
          @update:value="handleSelect"
          :theme-overrides="selectOverrides"
        />
      </div>
      <div class="display">
        <n-space vertical>
          <h3>设备信息:</h3>
          <p>名称: {{ curr_device?.name }}</p>
          <p>IP: {{ curr_device?.ip }}</p>
          <p>厂商: {{ curr_device?.vendor }}</p>
          <p>型号: {{ curr_device?.model }}</p>
          <p>高度: {{ curr_device?.height }}</p>
        </n-space>
      </div>
    </div>
  </div>
</template>

<style lang="css" scoped>
.container {
  height: 100%;
  overflow-y: scroll;
  position: relative;
  gap: 4px;
  display: flex;
  flex-direction: row;
}

.container::-webkit-scrollbar {
  width: 0;
  height: 0;
}

.rackcontainer {
  flex: 1;
  display: flex;
  /* flex-direction: column-reverse; */
}
/* 主容器：科技风背景 */
.rack {
  /* width: 220px; */
  flex: 1;
  height: fit-content;
  min-height: 0;
  border: 1px solid #455f87;
  border-radius: 4px;
  background: #0a0a1a;
  background: linear-gradient(180deg, var(--panel), var(--panel-soft));
  background-size:
    20px 20px,
    20px 20px,
    1px 1px,
    1px 1px;
  background-position:
    0 0,
    10px 10px,
    0 0,
    0 0;
  padding: 4px;
  display: grid;
  grid-template-columns: 30px 1fr 30px;
}

.displaycontainer {
  flex: 1;
  display: grid;
  grid-template-rows: 100px 1fr;
  position: sticky;
  top: 0px;
}
.select {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 6px;
}
.display {
  color: var(--text);
  padding: 12px 6px;
}

/* 左右侧刻度 */
.rackpositionl {
  display: grid;
  text-align: center;
  background-color: rgba(47, 47, 106, 0.5);
}

.rackpositionr {
  display: grid;
  text-align: center;
  background-color: rgba(47, 47, 106, 0.5);
}

.cell {
  display: flex;
  align-items: center;
  justify-content: center;
  /* background-color: rgba(10, 10, 30, 0.5); */
  border-right: 1px solid #404060;
  /* height: 12px; */
}

.cellrepeat {
  color: #40c0ff;
  font-weight: 500;
  grid-row: var(--row-height);
  background-color: transparent;
}

.last-cell {
  border-bottom: 1px solid #404060;
}

.side {
  margin: 0;
  padding: 0;
  text-align: center;
  white-space: nowrap;
  font-size: 10px;
  color: #40c0ff;
  text-shadow: 0 0 5px rgba(0, 200, 255, 0.8);
}

.rackmain {
  display: grid;
  border: 1px solid #455f87;
}

.celldevice {
  grid-row: var(--row-start) / var(--row-end);
  background: linear-gradient(180deg, var(--panel), var(--panel-soft));
  border: 1px solid #8fba2b;
  border-radius: 4px;
  margin: 0 1px;
  font-weight: 500;
  color: #a0f0ff;
  text-align: center;
}

.devicedetail {
  padding: 0;
  background:
    radial-gradient(circle at top left, rgba(58, 140, 202, 0.16), transparent 80%),
    linear-gradient(180deg, rgba(18, 40, 61, 0.96), rgba(12, 28, 44, 0.96));
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.03),
    0 10px 24px rgba(3, 12, 20, 0.28);
}

@keyframes glow {
  from {
    box-shadow: 0 0 8px rgba(0, 200, 255, 0.5);
  }
  to {
    box-shadow: 0 0 12px rgba(0, 200, 255, 0.8);
  }
}

.cellempty {
  grid-row: var(--row-start) / span 1;
  background-color: rgba(20, 20, 40, 0.3);
  font-size: 10px;
  color: #6688aa;
  border: 0;
  text-align: center;
}

.device-label {
  font-size: 10px;
  font-weight: 500;
  text-align: center;
  /* border-radius: 4px; */
  /* background-color: rgba(0, 0, 0, 0.6); */
  /* box-shadow: 0 0 5px rgba(0, 200, 255, 0.5); */
  overflow: hidden;
  /* text-overflow: ellipsis; */
  /* white-space: nowrap; */
}

.height-badge {
  margin-left: 4px;
  font-weight: normal;
  color: #40c0ff;
  background-color: rgba(0, 20, 40, 0.7);
  padding: 1px 3px;
  border-radius: 3px;
  border: 1px solid #40c0ff;
}

/* 颜色区分（柔和的霓虹风格） */
/* .celldevice:nth-child(2n + 1) {
  background: rgba(10, 20, 40, 0.7);
  border-color: #40c0ff;
  color: #a0f0ff;
} */

/* .celldevice:nth-child(n) {
  background: rgba(10, 20, 40, 0.7);
  border-color: #7d5dff;
  color: #b0a0ff;
} */

/* .celldevice:nth-child(4n + 1) {
  background: rgba(10, 20, 40, 0.7);
  border-color: #ff4080;
  color: #ff90b0;
} */

.celldevice:nth-child(n) {
  background: rgba(10, 20, 40, 0.7);
  border-color: #60ffcc;
  color: #a0ffdd;
}

/* .celldevice:nth-child(6n + 1) {
  background: rgba(10, 20, 40, 0.7);
  border-color: #ff8040;
  color: #ff9060;
} */

/* body {
  margin: 0;
  background: #0a0a1a;
  font-family: 'Courier New', 'Segoe UI', monospace;
} */
</style>
