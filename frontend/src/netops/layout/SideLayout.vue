<script setup lang="ts">
import { computed } from 'vue'
import { useLayoutStore } from '@netops/stores/layout'
import UserBar from '@netops/layout/UserBar.vue'
import SubMenuBar from '@netops/layout/SubMenuBar.vue'

const layoutStore = useLayoutStore()
const isCollapsed = computed(() => layoutStore.collapsed)
</script>

<template>
  <el-container class="side-layout" direction="horizontal">
    <el-aside :width="isCollapsed ? '64px' : '160px'" class="side-aside">
      <slot name="nav" />
    </el-aside>
    <el-container direction="vertical" class="side-content">
      <!-- 主页面左上角：当前一级分组下的递归子菜单 + 用户区 -->
      <header class="side-header">
        <SubMenuBar />
        <UserBar />
      </header>
      <el-main class="side-main">
        <slot name="main" />
      </el-main>
    </el-container>
  </el-container>
</template>

<style lang="css" scoped>
.side-layout { height: 100vh; }
.side-aside {
  overflow-y: auto;
  overflow-x: hidden;
  transition: width 0.3s;
  background: var(--el-fill-color-blank);
  border-right: 1px solid var(--el-border-color);
}
.side-header {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 42px;
  padding: 0 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
  flex-shrink: 0;
}
.side-main {
  flex: 1;
  padding: 0;
  overflow: auto;
  background: var(--el-bg-color-page);
}
</style>
