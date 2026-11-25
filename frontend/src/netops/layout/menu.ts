import { h } from 'vue'
import type { Component } from 'vue'
import { ElIcon } from 'element-plus'
import { DataAnalysis, Connection, Timer, Grid } from '@element-plus/icons-vue'
import type { MenuItem } from '@/types'
import {
  IconOverview, IconDevices, IconDeviceList, IconBaseline, IconInterfaces,
  IconParsers, IconConfig, IconLoadBalancer, IconDns, IconPolicy,
  IconIp, IconSubnet, IconTools, IconPathTrace, IconRouting,
  IconDoc, IconKnowledge,
} from '@/assets/menu-icons'

// 包装成 Element Plus 的 el-icon 渲染函数；只给侧栏一级菜单用
const renderIcon = (icon: Component) => {
  return () => h(ElIcon, null, { default: () => h(icon) })
}

/** 导航分组：侧栏只到一级 > 二级，三级放顶栏水平。 */
export const menuOptions: MenuItem[] = [
  { index: '/overview', label: '总览', icon: renderIcon(IconOverview) },
  {
    index: 'assets', label: '资产', icon: renderIcon(IconDevices),
    children: [
      {
        index: 'assets-host', label: '主机',
        children: [
          { index: '/asset/devices', label: '网络设备', icon: renderIcon(IconDeviceList) },
          { index: '/asset/physical', label: '物理机' },
          { index: '/asset/virtual', label: '虚拟机' },
        ],
      },
      {
        index: 'assets-network-service', label: '网络服务',
        children: [
          { index: '/asset/ip-addresses', label: 'IP 地址', icon: renderIcon(IconIp) },
          { index: '/asset/subnets', label: '网段', icon: renderIcon(IconSubnet) },
          { index: '/asset/cloud-network', label: '云资产' },
          { index: '/asset/load-balancer', label: '负载均衡' },
          { index: '/asset/domain', label: '域名' },
          { index: '/asset/link', label: '链路信息' },
        ],
      },
      {
        index: 'assets-application', label: '应用服务',
        children: [
          { index: '/asset/application', label: '应用系统' },
          { index: '/asset/database', label: '数据库实例' },
        ],
      },
    ],
  },
  {
    index: 'topology', label: '拓扑', icon: renderIcon(IconPathTrace),
    children: [
      { index: '/topology', label: '展示', icon: renderIcon(IconPathTrace) },
      { index: '/topology/edit', label: '编辑' },
    ],
  },
  {
    index: 'config', label: '配置', icon: renderIcon(IconConfig),
    children: [
      {
        index: 'config-firewall', label: '防火墙',
        children: [
          { index: '/config/policy', label: '访问策略', icon: renderIcon(IconPolicy) },
          { index: '/config/firewall', label: '地址转换(NAT)' },
          { index: '/config/address-service', label: '地址与服务对象' },
        ],
      },
      {
        index: 'config-lb', label: '负载均衡',
        children: [
          { index: '/config/slb', label: '本地LB(SLB)' },
          { index: '/config/gslb', label: '全局LB(GSLB)' },
          { index: '/config/cloud-lb', label: '云LB配置' },
        ],
      },
      {
        index: 'config-network', label: '网络基础',
        children: [
          { index: '/config/routing-table', label: '路由表', icon: renderIcon(IconRouting) },
          { index: '/config/arp-mac', label: 'ARP/MAC', icon: renderIcon(IconInterfaces) },
          { index: '/config/interfaces', label: '网卡/接口', icon: renderIcon(IconInterfaces) },
          { index: '/config/vlans', label: 'VLAN' },
          { index: '/config/vrf', label: 'VRF 实例' },
        ],
      },
      {
        index: 'config-baseline', label: '基线配置',
        children: [
          { index: '/config/baseline', label: '基线参数' },
          { index: '/config/accounts', label: '设备账号' },
          { index: '/config/cloud-accounts', label: '云平台账号' },
          { index: '/config/parsers', label: '解析器模板', icon: renderIcon(IconParsers) },
        ],
      },
    ],
  },
  {
    index: 'monitor', label: '监控', icon: renderIcon(Timer),
    children: [
      { index: '/monitor/tasks', label: '任务列表', icon: renderIcon(Timer) },
      { index: '/monitor/status', label: '运行监控', icon: renderIcon(DataAnalysis) },
    ],
  },
  {
    index: 'docs', label: '文档', icon: renderIcon(IconDoc),
    children: [
      { index: '/docs/knowledge', label: '知识库', icon: renderIcon(IconKnowledge) },
      { index: '/docs/spreadsheet', label: '电子表格', icon: renderIcon(Grid) },
    ],
  },
  {
    index: 'tools', label: '工具', icon: renderIcon(IconTools),
    children: [
      { index: '/tools/path-trace', label: '路径追踪', icon: renderIcon(IconPathTrace) },
      { index: '/tools/inspection', label: '巡检', icon: renderIcon(Timer) },
      { index: '/tools/rack-view', label: '机柜视图', icon: renderIcon(IconBaseline) },
      { index: '/tools/subnet-calc', label: '子网计算器', icon: renderIcon(IconSubnet) },
      { index: '/tools/dns-query', label: 'DNS 查询', icon: renderIcon(IconDns) },
      { index: '/tools/sls-query', label: 'SLS 日志查询' },
      { index: '/tools/internet-asset', label: '互联网资产分析', icon: renderIcon(DataAnalysis) },
      { index: '/tools/parser-mapping', label: '解析映射', icon: renderIcon(Connection) },
    ],
  },
]

/** 递归收集某个节点下的全部叶子路径 */
export const collectPaths = (item: MenuItem, out: string[] = []): string[] => {
  if (item.children?.length) {
    item.children.forEach((child) => collectPaths(child, out))
  } else if (item.index.startsWith('/')) {
    out.push(item.index)
  }
  return out
}

/** 取某个节点的第一个可路由叶子（点击分组时跳转用） */
export const firstPath = (item: MenuItem): string | undefined => {
  if (!item.children?.length) {
    return item.index.startsWith('/') ? item.index : undefined
  }
  for (const child of item.children) {
    const path = firstPath(child)
    if (path) return path
  }
  return undefined
}

/** 按当前路由反查所属一级分组：叶子路径取最长前缀匹配 */
export const findTopGroup = (path: string, items: MenuItem[] = menuOptions): MenuItem | undefined => {
  let matched: MenuItem | undefined
  let matchedLength = -1
  for (const item of items) {
    if (!item.children?.length) {
      if (item.index === path && item.index.length > matchedLength) {
        matched = item
        matchedLength = item.index.length
      }
      continue
    }
    for (const leaf of collectPaths(item)) {
      const hit = path === leaf || path.startsWith(`${leaf}/`)
      if (hit && leaf.length > matchedLength) {
        matched = item
        matchedLength = leaf.length
      }
    }
  }
  return matched
}

/** 在某个一级分组下，找到当前路由所属的二级节点（二级组或二级叶子） */
export const findSecondGroup = (path: string, top?: MenuItem): MenuItem | undefined => {
  if (!top?.children?.length) return undefined
  let matched: MenuItem | undefined
  let matchedLength = -1
  for (const second of top.children) {
    for (const leaf of collectPaths(second)) {
      const hit = path === leaf || path.startsWith(`${leaf}/`)
      if (hit && leaf.length > matchedLength) {
        matched = second
        matchedLength = leaf.length
      }
    }
  }
  return matched
}
