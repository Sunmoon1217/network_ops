<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { findTopGroup, findSecondGroup } from '@netops/layout/menu'
import MenuNode from '@netops/layout/MenuNode.vue'

const route = useRoute()

// 一级 / 二级留在侧栏，顶栏只渲染当前二级组下的三级菜单。
// 当前二级是叶子（如「配置」下的各页）时三级为空，顶栏只留用户区。
const top = computed(() => findTopGroup(route.path))
const second = computed(() => findSecondGroup(route.path, top.value))
const children = computed(() => second.value?.children ?? [])
</script>

<template>
  <div class="sub-menu-bar">
    <el-menu
      v-if="children.length"
      mode="horizontal"
      :default-active="route.path"
      class="sub-menu"
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
