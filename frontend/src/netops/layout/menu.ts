import { h } from 'vue'
import type { Component } from 'vue'
import { ElIcon } from 'element-plus'
import { DataAnalysis, Connection, Timer, Grid } from '@element-plus/icons-vue'
import type { MenuItem } from '@/types'
import {
  IconOverview, IconDevices, IconDeviceList, IconBaseline, IconInterfaces,
  IconParsers, IconConfig, IconLoadBalancer, IconDns, IconPolicy,
  IconIp, IconSubnet, IconTools, IconPathTrace, IconRouting,
  IconDoc, IconKnowledge, IconTemp,
} from '@/assets/menu-icons'

// 包装成 Element Plus 的 el-icon 渲染函数；只给侧栏一级菜单用
const renderIcon = (icon: Component) => {
  return () => h(ElIcon, null, { default: () => h(icon) })
}

/**
 * 导航分组：侧栏只渲染一级，主页面顶部渲染当前一级下的递归子菜单。
 * 约定：叶子节点的 index 就是路由路径（以 / 开头），分组节点的 index 是唯一 key。
 */
export const menuOptions: MenuItem[] = [
  { index: '/', label: '总览', icon: renderIcon(IconOverview) },
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
        index: 'assets-component', label: '组件',
        children: [
          { index: '/asset/interfaces', label: '网卡/接口', icon: renderIcon(IconInterfaces) },
          { index: '/asset/vlans', label: 'VLAN' },
        ],
      },
      {
        index: 'assets-network-service', label: '网络服务',
        children: [
          { index: '/asset/ip-addresses', label: 'IP 地址', icon: renderIcon(IconIp) },
          { index: '/asset/subnets', label: '网段', icon: renderIcon(IconSubnet) },
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
      { index: '/config/slb', label: '负载均衡', icon: renderIcon(IconLoadBalancer) },
      { index: '/config/gslb', label: '域名解析', icon: renderIcon(IconDns) },
      { index: '/config/firewall', label: 'NAT 管理', icon: renderIcon(IconPolicy) },
      { index: '/config/routing-table', label: '路由表', icon: renderIcon(IconRouting) },
      { index: '/config/arp-mac', label: 'ARP/MAC', icon: renderIcon(IconInterfaces) },
      { index: '/config/policy', label: '访问策略', icon: renderIcon(IconPolicy) },
      { index: '/config/baseline', label: '基线管理', icon: renderIcon(IconBaseline) },
      { index: '/config/parsers', label: '解析器模板', icon: renderIcon(IconParsers) },
      { index: '/config/accounts', label: '设备账号', icon: renderIcon(IconBaseline) },
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
      { index: '/docs/temp', label: '临时', icon: renderIcon(IconTemp) },
    ],
  },
  {
    index: 'tools', label: '工具', icon: renderIcon(IconTools),
    children: [
      { index: '/tools/path-trace', label: '路径追踪', icon: renderIcon(IconPathTrace) },
      { index: '/tools/rack-view', label: '机柜视图', icon: renderIcon(IconBaseline) },
      { index: '/tools/subnet-calc', label: '子网计算器', icon: renderIcon(IconSubnet) },
      { index: '/tools/dns-query', label: 'DNS 查询', icon: renderIcon(IconDns) },
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
