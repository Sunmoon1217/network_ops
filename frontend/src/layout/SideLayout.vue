<script setup lang="ts">
import { computed } from 'vue'
import { useLayoutStore } from '@/stores/layout'
import UserBar from '@/layout/UserBar.vue'

const layoutStore = useLayoutStore()
const isCollapsed = computed(() => layoutStore.collapsed)
</script>

<template>
  <el-container class="side-layout" direction="horizontal">
    <el-aside :width="isCollapsed ? '64px' : '160px'" class="side-aside">
      <slot name="nav" />
    </el-aside>
    <el-container direction="vertical" class="side-content">
      <UserBar />
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
.side-main {
  flex: 1;
  padding: 0;
  overflow: auto;
  background: var(--el-bg-color-page);
}
</style>
