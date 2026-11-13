<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useLayoutStore } from '@netops/stores/layout'
import { IconLayoutSide } from '@/assets/menu-icons'
import { menuOptions, findTopGroup, firstPath } from '@netops/layout/menu'

const route = useRoute()
const layoutStore = useLayoutStore()
const collapsed = computed(() => layoutStore.collapsed)

// 侧栏只放一级分组，当前分组由路由反查
const activeGroup = computed(() => findTopGroup(route.path)?.index)
</script>

<template>
  <div class="app-nav">
    <div class="nav-logo">
      <span v-if="!collapsed" class="logo-text"><strong>Network Ops</strong></span>
      <span v-else class="logo-icon"><strong>N</strong></span>
    </div>

    <el-menu
      mode="vertical"
      :default-active="activeGroup"
      :collapse="collapsed"
      class="app-menu"
    >
      <el-menu-item
        v-for="item in menuOptions"
        :key="item.index"
        :index="item.index"
        class="nav-item"
      >
        <el-icon><component :is="item.icon?.()?.children?.default" /></el-icon>
        <template #title><span>{{ item.label }}</span></template>
        <router-link
          :to="firstPath(item) ?? item.index"
          class="nav-link-overlay"
          :aria-label="item.label"
        />
      </el-menu-item>
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
/* 整个菜单项都是 <a>：中键新开 / 右键复制链接都可用，且不影响折叠时的图标 + tooltip */
.app-nav :deep(.nav-item) { position: relative; }
.app-nav :deep(.nav-link-overlay) {
  position: absolute;
  inset: 0;
  z-index: 1;
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
