<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import ZabbixAPI from '@/api/zabbix_api'
import {
  calculateUpRatioFromItems,
  createZabbixApiFromEnv,
  getItemsByGroupNameAndHostKeyword,
} from '@/api/dashboard_zabbix'
import BarCharts from '@/ui/BarCharts.vue'
import { useMessage } from 'naive-ui'

interface InterfaceUsageItem {
  name: string
  value: number
}

const zabbixEnv = import.meta.env as Record<string, string | undefined>
const zabbixApi = shallowRef<ZabbixAPI | null>(null)
const notCollectedValue = '未采集'
const message = useMessage()
const REGION_NAMES = [
  { region: '核心业务区', hostname: 'COREYW-AS' },
  { region: '互联网业务区', hostname: 'INTYW-AS' },
  { region: '管理业务区', hostname: 'MGTYW-AS' },
  { region: '办公业务区', hostname: 'OAYW-AS' },
  { region: '互联网DMZ', hostname: 'INT-AS' },
  { region: '云平台', hostname: 'ASW' },
] as const
const INTERFACE_STATUS_KEYWORDS = ['ifoperstatus', '运行状态', 'oper status', '接口状态']

const interfacesData = ref<InterfaceUsageItem[]>(
  REGION_NAMES.map((name) => ({
    name: name.region,
    value: 0,
  })),
)

const peak = computed(() =>
  interfacesData.value.reduce((max, item) => (item.value > max.value ? item : max), {
    name: notCollectedValue,
    value: 0,
  }),
)

const avgUsage = computed(() => {
  const validValues = interfacesData.value.map((item) => item.value).filter((value) => value > 0)
  if (!validValues.length) return notCollectedValue
  return `${Math.round(validValues.reduce((sum, item) => sum + item, 0) / validValues.length)}%`
})

const ensureZabbixApi = async (): Promise<ZabbixAPI> => {
  if (zabbixApi.value) return zabbixApi.value
  const api = await createZabbixApiFromEnv(zabbixEnv, message)
  zabbixApi.value = api
  return api
}

const fetchInterfaceUsage = async () => {
  try {
    const api = await ensureZabbixApi()
    const data = await Promise.all(
      REGION_NAMES.map(async (regionName) => {
        const result = await getItemsByGroupNameAndHostKeyword(
          api,
          regionName.region,
          regionName.hostname,
          INTERFACE_STATUS_KEYWORDS,
        )
        if (!result || !result.items?.length) {
          return { name: regionName.region, value: 0 }
        }

        const upRatio = calculateUpRatioFromItems(result.items)
        return {
          name: regionName.region,
          value: upRatio.ratio,
        }
      }),
    )

    interfacesData.value = data
  } catch (error) {
    console.error('Failed to fetch regional interface usage:', error)
    interfacesData.value = REGION_NAMES.map((name) => ({ name: name.region, value: 0 }))
  }
}

onMounted(() => {
  fetchInterfaceUsage()
})

onBeforeUnmount(() => {
  zabbixApi.value?.logout()
})
</script>
<template>
  <div class="container">
    <div class="summary">
      <article class="summary-card">
        <p>平均使用率</p>
        <strong>{{ avgUsage }}</strong>
      </article>
      <article class="summary-card">
        <p>峰值区域</p>
        <strong>{{ peak.value > 0 ? peak.name : notCollectedValue }}</strong>
      </article>
    </div>
    <div class="chart-wrap">
      <BarCharts :data="interfacesData" />
    </div>
  </div>
</template>
<style lang="css" scoped>
.container {
  width: 100%;
  height: 100%;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 6px;
  min-height: 0;
}

.summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.summary-card {
  border: 1px solid rgba(111, 244, 255, 0.16);
  border-radius: 12px;
  padding: 6px 10px;
  background: rgba(255, 255, 255, 0.03);
}

.summary-card p {
  margin: 0;
  font-size: 12px;
  color: #9fc4df;
}

.summary-card strong {
  margin-top: 3px;
  display: block;
  font-size: 16px;
  color: #6ff4ff;
  line-height: 1;
}

.chart-wrap {
  height: 100%;
  min-height: 0;
}

.chart-wrap > * {
  min-width: 0;
  min-height: 0;
}
</style>
