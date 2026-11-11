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
  <el-menu-item v-else :index="item.index">{{ item.label }}</el-menu-item>
</template>
