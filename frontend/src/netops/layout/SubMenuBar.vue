<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { findTopGroup } from '@netops/layout/menu'
import MenuNode from '@netops/layout/MenuNode.vue'

const route = useRoute()
const router = useRouter()

// 当前路由归属的一级分组 → 渲染它下面的递归子菜单
const children = computed(() => findTopGroup(route.path)?.children ?? [])

const handleSelect = (index: string) => {
  if (index.startsWith('/')) router.push(index)
}
</script>

<template>
  <div class="sub-menu-bar">
    <el-menu
      v-if="children.length"
      mode="horizontal"
      :default-active="route.path"
      class="sub-menu"
      @select="handleSelect"
    >
      <MenuNode v-for="item in children" :key="item.index" :item="item" />
    </el-menu>
  </div>
</template>

<style scoped>
.sub-menu-bar {
  flex: 1;
  min-width: 0;
  overflow-x: auto;
  overflow-y: hidden;
}
.sub-menu-bar :deep(.el-menu) {
  width: max-content;
  min-width: 100%;
  height: 42px;
  border-bottom: none;
  background: transparent;
}
.sub-menu-bar :deep(.el-menu-item),
.sub-menu-bar :deep(.el-sub-menu__title) {
  height: 42px;
  line-height: 42px;
  padding: 0 12px;
}
</style>
