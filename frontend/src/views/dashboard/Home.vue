<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import api from '@/api/index'
import StatCard from '@/ui/StatCard.vue'
import ChartCard from '@/ui/ChartCard.vue'
import { pieOpt, barOpt, gaugeOpt, lookup, mapItems } from '@/composables/useEcharts'

const data = ref<any>(null)
const loading = ref(true)

onMounted(async () => {
  try {
    const resp = await api.get('/api/assets/overview/')
    data.value = resp.data
  } finally {
    loading.value = false
  }
})

const charts = ref<any[]>([])

watch(data, (val) => { if (val) buildCharts() })

const buildCharts = () => {
  const d = data.value
  const list: any[] = []

  if (d.cabinets_by_dc?.length)
    list.push({ title: '机柜 / 数据中心', option: barOpt('机柜 / 数据中心', d.cabinets_by_dc.map((i: any) => i.room__datacenter__name || '未知'), d.cabinets_by_dc.map((i: any) => i.count)) })
  if (d.cabinets_by_status?.length)
    list.push({ title: '机柜状态', option: pieOpt('机柜状态', mapItems(d.cabinets_by_status.map((i: any) => ({ name: i.status === 'active' ? '在用' : '空闲', value: i.count })))) })
  if (d.device_types?.length)
    list.push({ title: '设备类型', option: pieOpt('设备类型', mapItems(d.device_types.map((i: any) => ({ name: lookup({ firewall: '防火墙', switch: '交换机', slb: '服务器负载均衡', gslb: '全局负载均衡', router: '路由器', server: '服务器', dns: '域名解析', dwdm: '波分复用', internalac: '上网行为管理', wirelessac: '无线控制器' }, i.device_type, i.device_type), value: i.count })))) })
  if (d.devices_by_vendor?.length)
    list.push({ title: '设备 / 厂商', option: barOpt('设备 / 厂商', d.devices_by_vendor.map((i: any) => i.device_model__vendor__name || '未知'), d.devices_by_vendor.map((i: any) => i.count), true) })
  if (d.devices_by_zone?.length)
    list.push({ title: '设备 / 安全域', option: barOpt('设备 / 安全域', d.devices_by_zone.map((i: any) => i.security_zone__name || '未分配'), d.devices_by_zone.map((i: any) => i.count)) })
  if (d.interface_count > 0)
    list.push({ title: '接口状态', option: gaugeOpt('接口启用率', d.interface_up, d.interface_count || 1) })
  if (d.interface_modes?.length)
    list.push({ title: '接口模式', option: pieOpt('接口模式', mapItems(d.interface_modes.map((i: any) => ({ name: lookup({ layer3: '三层', access: 'Access', trunk: 'Trunk', hybrid: 'Hybrid' }, i.mode || '', '未设置'), value: i.count })))) })
  if (d.route_protocols?.length)
    list.push({ title: '路由协议', option: pieOpt('路由协议分布', mapItems(d.route_protocols.map((i: any) => ({ name: lookup({ static: '静态', connected: '直连', ospf: 'OSPF', bgp: 'BGP', rip: 'RIP', other: '其他' }, i.protocol, i.protocol), value: i.count })))) })
  if (d.routes_by_device?.length)
    list.push({ title: '路由 / 设备', option: barOpt('路由 / 设备 (Top 10)', d.routes_by_device.map((i: any) => i.vrf__device__hostname || '未知'), d.routes_by_device.map((i: any) => i.count), true) })
  if (d.vs_by_protocol?.length)
    list.push({ title: 'VS 协议', option: pieOpt('虚拟服务协议', mapItems(d.vs_by_protocol.map((i: any) => ({ name: (i.protocol || 'tcp').toUpperCase(), value: i.count })))) })
  if (d.pools_by_lb?.length)
    list.push({ title: '池 / LB设备', option: barOpt('池 / LB 设备', d.pools_by_lb.map((i: any) => i.device__hostname || '未知'), d.pools_by_lb.map((i: any) => i.count), true) })
  if (d.policies_by_action?.length)
    list.push({ title: '策略动作', option: pieOpt('安全策略动作', mapItems(d.policies_by_action.map((i: any) => ({ name: i.action === 'allow' ? '放行' : '拒绝', value: i.count })))) })
  if (d.nat_by_type?.length)
    list.push({ title: 'NAT 类型', option: pieOpt('NAT 规则类型', mapItems(d.nat_by_type.map((i: any) => ({ name: lookup({ snat: '源转换', dnat: '目的转换', dulnat: '双向转换' }, i.nat_type, i.nat_type), value: i.count })))) })
  if (d.address_books_by_type?.length)
    list.push({ title: '地址簿类型', option: pieOpt('地址簿类型', mapItems(d.address_books_by_type.map((i: any) => ({ name: lookup({ host: '主机', subnet: '子网', range: '范围', addressbook: '地址簿组' }, i.address_type, i.address_type), value: i.count })))) })
  if (d.services_by_protocol?.length)
    list.push({ title: '服务协议', option: pieOpt('服务协议分布', mapItems(d.services_by_protocol.map((i: any) => ({ name: (i.protocol || 'tcp').toUpperCase(), value: i.count })))) })
  if (d.subnets_by_dc?.length)
    list.push({ title: '子网 / 数据中心', option: barOpt('子网 / 数据中心', d.subnets_by_dc.map((i: any) => i.datacenter__name || '未分配'), d.subnets_by_dc.map((i: any) => i.count)) })
  if (d.subnets_by_zone?.length)
    list.push({ title: '子网 / 安全域', option: barOpt('子网 / 安全域', d.subnets_by_zone.map((i: any) => i.security_zone__name || '未分配'), d.subnets_by_zone.map((i: any) => i.count), true) })

  charts.value = list
}
</script>

<template>
  <div v-loading="loading" class="dashboard">
    <template v-if="data">
      <div class="summary-row">
        <StatCard v-for="s in [
          { label: '设备', value: data.device_count, color: '#5470c6' },
          { label: '接口', value: data.interface_count, color: '#91cc75' },
          { label: '路由', value: data.route_count, color: '#fac858' },
          { label: '策略', value: data.policy_count, color: '#ee6666' },
          { label: 'NAT', value: data.nat_rule_count, color: '#73c0de' },
          { label: '子网', value: data.subnet_count, color: '#3ba272' },
          { label: 'VS', value: data.vs_count, color: '#9a60b4' },
        ]" :key="s.label" :label="s.label" :value="s.value" :color="s.color" style="flex: 1; min-width: 110px;" />
      </div>

      <div class="chart-grid">
        <ChartCard v-for="chart in charts" :key="chart.title" :option="chart.option" />
      </div>

      <div class="count-grid">
        <StatCard v-for="item in [
          { label: '数据中心', value: data.dc_count, icon: '🏢' },
          { label: '机房', value: data.room_count, icon: '🏠' },
          { label: '安全域', value: data.security_zone_count, icon: '🔒' },
          { label: '厂商', value: data.vendor_count, icon: '🏭' },
          { label: '设备型号', value: data.device_model_count, icon: '📦' },
          { label: 'VLAN', value: data.vlan_count, icon: '🔗' },
          { label: 'VRF', value: data.vrf_count, icon: '🌐' },
          { label: '地址簿', value: data.address_book_count, icon: '📋' },
          { label: '服务', value: data.service_count, icon: '⚙️' },
          { label: 'GTM 域名', value: data.gtm_wideip_count, icon: '🌍' },
          { label: 'GTM 池', value: data.gtm_pool_count, icon: '🔄' },
          { label: 'GTM DC', value: data.gtm_dc_count, icon: '📡' },
        ]" :key="item.label" :label="item.label" :value="item.value" :icon="item.icon" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.dashboard { padding: 16px; display: flex; flex-direction: column; gap: 20px; }
.summary-row { display: flex; gap: 12px; flex-wrap: wrap; }
.chart-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 16px; }
.count-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
</style>
