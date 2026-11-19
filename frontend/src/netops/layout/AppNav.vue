<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useLayoutStore } from '@netops/stores/layout'
import { IconLayoutSide } from '@/assets/menu-icons'
import type { MenuItem } from '@/types'
import { menuOptions, findTopGroup, findSecondGroup, firstPath } from '@netops/layout/menu'

const route = useRoute()
const layoutStore = useLayoutStore()
const collapsed = computed(() => layoutStore.collapsed)

// 当前路由归属的一级 / 二级。二级组（自己还有三级）用组 key 高亮，
// 一级叶子与二级叶子用路由路径——这样三级菜单移走后，侧栏仍能标出所在分组。
const activeIndex = computed(() => {
  const top = findTopGroup(route.path)
  const second = findSecondGroup(route.path, top)
  if (second?.children?.length) return second.index
  return second?.index ?? top?.index ?? route.path
})

// 二级项点击目标：二级组去它的第一个三级叶子，二级叶子就是自己
const targetOf = (item: MenuItem) => (item.children?.length ? (firstPath(item) ?? item.index) : item.index)
</script>

<template>
  <div class="app-nav">
    <div class="nav-logo">
      <span v-if="!collapsed" class="logo-text"><strong>Network Ops</strong></span>
      <span v-else class="logo-icon"><strong>N</strong></span>
    </div>

    <el-menu
      mode="vertical"
      :default-active="activeIndex"
      :collapse="collapsed"
      :unique-opened="true"
      class="app-menu"
    >
      <template v-for="item in menuOptions" :key="item.index">
        <!-- 一级叶子（总览） -->
        <el-menu-item v-if="!item.children?.length" :index="item.index" class="nav-item">
          <el-icon><component :is="item.icon?.()?.children?.default" /></el-icon>
          <template #title><span>{{ item.label }}</span></template>
          <router-link :to="item.index" class="nav-link-overlay" :aria-label="item.label" />
        </el-menu-item>

        <!-- 一级分组：展开后是一级下的二级菜单；三级菜单在顶栏（SubMenuBar） -->
        <el-sub-menu v-else :index="item.index">
          <template #title>
            <el-icon><component :is="item.icon?.()?.children?.default" /></el-icon>
            <span>{{ item.label }}</span>
          </template>
          <el-menu-item
            v-for="second in item.children"
            :key="second.index"
            :index="second.index"
            class="nav-item"
          >
            <template #title><span>{{ second.label }}</span></template>
            <router-link :to="targetOf(second)" class="nav-link-overlay" :aria-label="second.label" />
          </el-menu-item>
        </el-sub-menu>
      </template>
    </el-menu>

    <div class="nav-collapse" @click="layoutStore.toggleCollapsed">
      <el-icon :class="{ collapsed }" :size="18"><component :is="IconLayoutSide" /></el-icon>
    </div>
  </div>
</template>

<style scoped>
.app-nav {
  /* el-menu 默认会铺自己的底色和 hover 底色，这里全部交给侧栏本体 */
  --el-menu-bg-color: transparent;
  --el-menu-hover-bg-color: transparent;
  --el-menu-text-color: var(--el-color-white);
  --el-menu-active-color: var(--el-color-white);
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
/* 一级菜单：半透明白块叠在深色导航本体上，文字白色 */
.app-nav :deep(.app-menu > .el-menu-item),
.app-nav :deep(.app-menu > .el-sub-menu > .el-sub-menu__title) {
  background: transparent;
  background: color-mix(in srgb, var(--el-color-white) 7%, transparent);
  color: var(--el-color-white);
}
.app-nav :deep(.app-menu > .el-menu-item .el-icon),
.app-nav :deep(.app-menu > .el-sub-menu > .el-sub-menu__title .el-icon) {
  color: var(--el-color-white);
}
.app-nav :deep(.app-menu > .el-menu-item:hover),
.app-nav :deep(.app-menu > .el-sub-menu > .el-sub-menu__title:hover) {
  background: color-mix(in srgb, var(--el-color-white) 12%, transparent);
}
.app-nav :deep(.app-menu > .el-menu-item.is-active),
.app-nav :deep(.app-menu > .el-sub-menu.is-active > .el-sub-menu__title) {
  background: color-mix(in srgb, var(--el-color-white) 10%, transparent);
  color: var(--el-color-white);
}
/* 二级菜单：主题色文字，hover / 选中用主题色的半透明底 */
.app-nav :deep(.app-menu > .el-sub-menu > .el-menu > .el-menu-item) {
  color: var(--el-color-primary);
}
.app-nav :deep(.app-menu > .el-sub-menu > .el-menu > .el-menu-item:hover) {
  background: color-mix(in srgb, var(--el-color-primary) 16%, transparent);
  color: var(--el-color-primary-light-3);
}
.app-nav :deep(.app-menu > .el-sub-menu > .el-menu > .el-menu-item.is-active) {
  background: color-mix(in srgb, var(--el-color-primary) 22%, transparent);
  color: var(--el-color-primary-light-3);
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
  border-bottom-color: color-mix(in srgb, var(--el-color-white) 12%, transparent);
  flex-shrink: 0;
}
.logo-text { font-size: 1rem; font-weight: 600; color: var(--el-color-white); }
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
  border-top-color: color-mix(in srgb, var(--el-color-white) 12%, transparent);
  cursor: pointer;
  color: var(--el-color-white);
  color: color-mix(in srgb, var(--el-color-white) 65%, transparent);
}
.nav-collapse:hover { background: color-mix(in srgb, var(--el-color-white) 8%, transparent); }
.nav-collapse .collapsed { transform: rotate(180deg); }
</style>
