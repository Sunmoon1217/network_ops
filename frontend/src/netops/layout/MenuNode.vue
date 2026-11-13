<script setup lang="ts">
import type { MenuItem } from '@/types'

defineOptions({ name: 'MenuNode' })

defineProps<{ item: MenuItem }>()
</script>

<template>
  <el-sub-menu v-if="item.children?.length" :index="item.index">
    <template #title><span>{{ item.label }}</span></template>
    <MenuNode v-for="child in item.children" :key="child.index" :item="child" />
  </el-sub-menu>
  <el-menu-item v-else :index="item.index">
    <router-link :to="item.index" class="menu-node-link">{{ item.label }}</router-link>
  </el-menu-item>
</template>

<style scoped>
.menu-node-link {
  display: inline-flex;
  align-items: center;
  width: 100%;
  height: 100%;
  color: inherit;
  text-decoration: none;
}
</style>
