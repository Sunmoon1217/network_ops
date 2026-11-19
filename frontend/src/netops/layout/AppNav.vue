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
/* 一级菜单（总览与各分组标题）用品牌色的低饱和浅底：color-mix 把主色按比例
   混进侧栏底色，亮/暗模式都得到同色相的灰调，不会像实色底那样抢眼。
   二级项保持透明，靠缩进区分层级。 */
.app-nav :deep(.app-menu > .el-menu-item),
.app-nav :deep(.app-menu > .el-sub-menu > .el-sub-menu__title) {
  background: var(--el-fill-color-light);
  background: color-mix(in srgb, var(--el-color-primary) 18%, var(--el-fill-color-blank));
  color: var(--el-text-color-primary);
}
/* hover 略微加深，选中态再深一档；文字沿用主题色（浅底上亮/暗都可读） */
.app-nav :deep(.app-menu > .el-menu-item:hover),
.app-nav :deep(.app-menu > .el-sub-menu > .el-sub-menu__title:hover) {
  background: var(--el-fill-color);
  background: color-mix(in srgb, var(--el-color-primary) 30%, var(--el-fill-color-blank));
}
.app-nav :deep(.app-menu > .el-menu-item.is-active),
.app-nav :deep(.app-menu > .el-sub-menu.is-active > .el-sub-menu__title) {
  background: var(--el-fill-color-dark);
  background: color-mix(in srgb, var(--el-color-primary) 26%, var(--el-fill-color-blank));
  color: var(--el-text-color-primary);
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
