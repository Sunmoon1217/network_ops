<script setup lang="ts">
import { h, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElIcon } from 'element-plus'
import type { Component } from 'vue'
import { useLayoutStore } from '@/stores/layout'
import {
  IconOverview, IconDevices, IconDeviceList, IconBaseline, IconInterfaces,
  IconParsers, IconConfig, IconLoadBalancer, IconDns, IconPolicy,
  IconIp, IconSubnet, IconTools, IconPathTrace, IconRouting,
  IconLayoutSide,
} from './menu-icons'

const router = useRouter()
const route = useRoute()
const layoutStore = useLayoutStore()
const collapsed = computed(() => layoutStore.collapsed)

const renderIcon = (icon: Component) => {
  return () => h(ElIcon, null, { default: () => h(icon) })
}

interface MenuItem {
  index: string
  label: string
  icon?: () => any
  children?: MenuItem[]
}

const menuOptions: MenuItem[] = [
  { index: '/', label: '总览', icon: renderIcon(IconOverview) },
  {
    index: '/devices', label: '设备管理', icon: renderIcon(IconDevices),
    children: [
      { index: '/devices', label: '设备列表', icon: renderIcon(IconDeviceList) },
      { index: '/devices/interfaces', label: '接口管理', icon: renderIcon(IconInterfaces) },
      { index: '/devices/baseline', label: '基线管理', icon: renderIcon(IconBaseline) },
      { index: '/devices/parsers', label: '解析器模板', icon: renderIcon(IconParsers) },
      { index: '/devices/accounts', label: '设备账号', icon: renderIcon(IconBaseline) },
      { index: '/devices/vlans', label: 'VLAN 管理', icon: renderIcon(IconInterfaces) },
    ],
  },
  {
    index: '/topology', label: '网络拓扑', icon: renderIcon(IconPathTrace),
    children: [
      { index: '/topology', label: '拓扑图', icon: renderIcon(IconPathTrace) },
    ],
  },
  {
    index: '/config', label: '配置管理', icon: renderIcon(IconConfig),
    children: [
      { index: '/config/slb', label: '负载均衡', icon: renderIcon(IconLoadBalancer) },
      { index: '/config/gslb', label: '域名解析', icon: renderIcon(IconDns) },
      { index: '/config/firewall', label: '防火墙策略', icon: renderIcon(IconPolicy) },
      { index: '/config/routing-table', label: '路由表', icon: renderIcon(IconRouting) },
      { index: '/config/arp-mac', label: 'ARP/MAC', icon: renderIcon(IconInterfaces) },
      { index: '/config/policy', label: '访问策略', icon: renderIcon(IconPolicy) },
    ],
  },
  {
    index: '/ipam', label: 'IP 管理', icon: renderIcon(IconIp),
    children: [
      { index: '/ipam/subnets', label: '网段管理', icon: renderIcon(IconSubnet) },
      { index: '/ipam/ip-addresses', label: 'IP 地址', icon: renderIcon(IconIp) },
      { index: '/ipam/tags', label: '标签管理', icon: renderIcon(IconIp) },
      { index: '/ipam/usage-trend', label: '使用率趋势', icon: renderIcon(IconSubnet) },
    ],
  },
  {
    index: '/tools', label: '工具', icon: renderIcon(IconTools),
    children: [
      { index: '/tools/path-trace', label: '路径追踪', icon: renderIcon(IconPathTrace) },
      { index: '/tools/rack-view', label: '机柜视图', icon: renderIcon(IconBaseline) },
      { index: '/tools/subnet-calc', label: '子网计算器', icon: renderIcon(IconSubnet) },
      { index: '/tools/dns-query', label: 'DNS 查询', icon: renderIcon(IconDns) },
    ],
  },
]

const handleMenuSelect = (index: string) => {
  if (index.startsWith('/')) router.push(index)
}
</script>

<template>
  <div class="app-nav">
    <div class="nav-logo">
      <span v-if="!collapsed" class="logo-text"><strong>Network Ops</strong></span>
      <span v-else class="logo-icon"><strong>N</strong></span>
    </div>

    <el-menu
      mode="vertical"
      :default-active="route.path"
      :collapse="collapsed"
      unique-opened
      class="app-menu"
      @select="handleMenuSelect"
    >
      <template v-for="item in menuOptions" :key="item.index">
        <el-sub-menu v-if="item.children" :index="item.index">
          <template #title>
            <el-icon><component :is="item.icon?.()?.children?.default" /></el-icon>
            <span>{{ item.label }}</span>
          </template>
          <el-menu-item v-for="child in item.children" :key="child.index" :index="child.index">
            <el-icon><component :is="child.icon?.()?.children?.default" /></el-icon>
            <span>{{ child.label }}</span>
          </el-menu-item>
        </el-sub-menu>
        <el-menu-item v-else :index="item.index">
          <el-icon><component :is="item.icon?.()?.children?.default" /></el-icon>
          <span>{{ item.label }}</span>
        </el-menu-item>
      </template>
    </el-menu>

    <div class="nav-collapse" @click="layoutStore.toggleCollapsed">
      <el-icon :class="{ collapsed }" :size="18"><component :is="IconLayoutSide" /></el-icon>
    </div>
  </div>
</template>

<style scoped>
.app-nav {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 0;
}
.app-nav :deep(.el-menu) {
  width: 100%;
  flex: 1;
  border-right: none;
}
.nav-logo {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 42px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0;
}
.logo-text { font-size: 1rem; font-weight: 600; color: var(--el-text-color-primary); }
.logo-icon { font-size: 1.2rem; color: var(--el-color-primary); }
.nav-collapse {
  position: absolute;
  bottom: 0;
  left: 0;
  width: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 36px;
  border-top: 1px solid var(--el-border-color-lighter);
  cursor: pointer;
  color: var(--el-text-color-secondary);
}
.nav-collapse:hover { background: var(--el-fill-color-light); }
.nav-collapse .collapsed { transform: rotate(180deg); }
</style>
