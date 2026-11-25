<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { findTopGroup, findSecondGroup, collectPaths } from '@netops/layout/menu'

const route = useRoute()
const router = useRouter()

// 一级 / 二级留在侧栏，顶栏放一个下拉触发器：当前二级组名下的所有三级项。
const top = computed(() => findTopGroup(route.path))
const second = computed(() => findSecondGroup(route.path, top.value))
const children = computed(() => second.value?.children ?? [])

// 当前激活的三级项 label（用于触发器显示）
const currentLabel = computed(() => {
  for (const child of children.value) {
    for (const leaf of collectPaths(child)) {
      if (route.path === leaf || route.path.startsWith(`${leaf}/`)) {
        return child.label
      }
    }
  }
  return ''
})

const handleCommand = (path: string) => {
  router.push(path)
}
</script>

<template>
  <div class="sub-menu-bar">
    <template v-if="children.length">
      <el-dropdown trigger="click" @command="handleCommand">
        <span class="dropdown-trigger">
          <span v-if="second?.label" class="trigger-group">{{ second.label }}</span>
          <span class="trigger-sep">/</span>
          <span class="trigger-current">{{ currentLabel }}</span>
          <el-icon class="trigger-arrow"><svg viewBox="0 0 1024 1024" width="14" height="14"><path d="M512 664a32 32 0 0 1-22.624-9.376l-288-288a32 32 0 1 1 45.248-45.248L512 587.776l265.376-266.4a32 32 0 1 1 45.248 45.248l-288 288A32 32 0 0 1 512 664z" fill="currentColor"/></svg></el-icon>
        </span>
        <template #dropdown>
          <el-dropdown-menu class="sub-menu-dropdown">
            <el-dropdown-item
              v-for="child in children"
              :key="child.index"
              :command="child.index"
              :class="{ 'is-active': currentLabel === child.label }"
            >
              {{ child.label }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </template>
  </div>
</template>

<style scoped>
.sub-menu-bar {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
}
.dropdown-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 10px;
  cursor: pointer;
  border-radius: 4px;
  font-size: 14px;
  color: var(--el-text-color-regular);
  transition: background-color 0.15s;
}
.dropdown-trigger:hover {
  background: var(--el-fill-color-light);
  color: var(--el-color-primary);
}
.trigger-group {
  font-weight: 600;
}
.trigger-sep {
  color: var(--el-text-color-placeholder);
}
.trigger-arrow {
  color: var(--el-text-color-placeholder);
  transition: transform 0.2s;
}
.dropdown-trigger:hover .trigger-arrow {
  color: var(--el-color-primary);
}
.sub-menu-dropdown :deep(.el-dropdown-menu__item.is-active) {
  color: var(--el-color-primary);
  font-weight: 600;
}
</style>
