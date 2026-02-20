<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElIcon } from 'element-plus'
import {
  HomeFilled,
  Monitor,
  DocumentChecked,
  Document,
  ArrowDown,
  Link,
  Lock,
  DataAnalysis,
  Connection,
} from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()

// 定义导航项类型
import type { Component } from 'vue'

interface NavItem {
  name: string
  path: string
  icon: Component
  children?: NavItem[]
}

const navItems: NavItem[] = [
  {
    name: '首页',
    path: '/',
    icon: HomeFilled, // 保持不变 - 主页图标
  },
  {
    name: '设备管理',
    path: '/devices',
    icon: Monitor, // 更换为 - 显示器图标（更代表设备）
  },
  {
    name: '配置管理',
    path: '#',
    icon: DocumentChecked, // 更换为 - 文档检查图标（更代表配置审核）
    children: [
      {
        name: '基线配置',
        path: '/configs/baseline',
        icon: DocumentChecked, // 更换为 - 文档检查图标（代表基线审核）
      },
      {
        name: '接口配置',
        path: '/config/interfaces',
        icon: Link, // 更换为 - 链接图标（代表网络接口）
      },
      {
        name: '访问策略',
        path: '/config/policy',
        icon: Lock, // 更换为 - 锁图标（代表访问控制）
      },
      {
        name: '负载均衡',
        path: '/config/load_balancer',
        icon: DataAnalysis, // 更换为 - 数据分析图标（代表负载分析）
      },
      {
        name: 'DNS',
        path: '/config/dns',
        icon: Connection, // 更换为 - 连接图标（代表域名解析连接）
      },
    ],
  },
  {
    name: '文档中心',
    path: '/docs',
    icon: Document, // 保持不变 - 文档图标
  },
]

// 控制下拉菜单显示的状态
const activeDropdown = ref<string | null>(null)

// 检查导航项是否激活
const isActive = (path: string) => {
  if (path === '#') return false
  return route.path === path || route.path.startsWith(`${path}/`)
}

// 检查是否有子菜单
const hasChildren = (item: NavItem) => {
  return item.children && item.children.length > 0
}

// 处理导航点击
const handleNavClick = (item: NavItem) => {
  if (!hasChildren(item)) {
    router.push(item.path)
    activeDropdown.value = null
  }
}
</script>

<template>
  <div class="navbar-container">
    <div class="navbar-logo">
      <ElIcon ><HomeFilled /></ElIcon>
      <span class="logo-text">网络运维平台</span>
    </div>
    <div class="menu-container">
      <ul class="nav-menu">
        <!-- 导航项渲染 -->
        <li
          v-for="item in navItems"
          :key="item.path"
          class="nav-item"
          :class="{
            active: isActive(item.path) || activeDropdown === item.path,
            'dropdown-item': hasChildren(item),
          }"
          @mouseenter="hasChildren(item) && (activeDropdown = item.path)"
          @mouseleave="hasChildren(item) && (activeDropdown = null)"
        >
          <!-- 导航项内容 -->
          <div
            :class="hasChildren(item) ? 'dropdown-toggle' : 'nav-item-content'"
            @click="handleNavClick(item)"
          >
            <ElIcon class="nav-icon"><component :is="item.icon" /></ElIcon>
            <span class="nav-text">{{ item.name }}</span>
            <ElIcon v-if="hasChildren(item)" class="dropdown-icon"><ArrowDown /></ElIcon>
          </div>

          <!-- 自定义下拉菜单 -->
          <div
            v-if="hasChildren(item) && activeDropdown === item.path"
            class="custom-dropdown-menu"
          >
            <div
              v-for="child in item.children"
              :key="child.path"
              class="dropdown-menu-item"
              :class="{ active: isActive(child.path) }"
              @click="handleNavClick(child)"
            >
              <ElIcon class="nav-icon"><component :is="child.icon" /></ElIcon>
              <span>{{ child.name }}</span>
            </div>
          </div>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.navbar-container {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  padding: 0 20px;
}

.navbar-logo {
  display: flex;
  align-items: center;
  height: 100%;
  gap: 10px;
  font-size: 1.2rem;
  font-weight: bold;
  color: white;
}

.logo-text {
  font-size: 1.1rem;
}

.menu-container {
  flex: 1;
  height: 100%;
  display: flex;
  justify-content: flex-start;
  margin-left: 40px;
}

.nav-menu {
  display: flex;
  list-style: none;
  margin: 0;
  padding: 0;
  gap: 10px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 16px;
  color: white;
  cursor: pointer;
  transition: background-color 0.3s ease;
  border-radius: 4px;
}

.nav-item:hover {
  background-color: #34495e;
}

.nav-item.active {
  background-color: #409eff;
  font-weight: bold;
}

.nav-icon {
  font-size: 1.1rem;
}

.nav-text {
  font-size: 0.95rem;
}

/* 导航项内容样式 */
.nav-item-content,
.dropdown-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  height: 100%;
  padding: 0 16px;
  /* line-height: 60px; */
  color: white;
  cursor: pointer;
  transition: background-color 0.3s ease;
  border-radius: 4px;
}

/* 下拉菜单样式 */
.dropdown-item {
  position: relative;
}

.dropdown-icon {
  font-size: 0.8rem;
  margin-left: 4px;
  transition: transform 0.3s ease;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 下拉菜单样式 */
.custom-dropdown-menu {
  position: absolute;
  top: 100%;
  left: 0;
  background-color: #2c3e50;
  border-radius: 4px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
  z-index: 1000;
  min-width: 140px;
  margin-top: 0;
  padding: 4px 0;
}

.dropdown-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 33px;
  padding: 0 16px;
  color: white;
  cursor: pointer;
  transition: background-color 0.3s ease;
}

.dropdown-menu-item:hover {
  background-color: #34495e;
}

.dropdown-menu-item.active {
  background-color: #409eff;
  font-weight: bold;
}

/* 图标样式统一 */
.nav-icon {
  font-size: 1.1rem;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
