<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { IconSun, IconMoon } from '@/assets/menu-icons'

const authStore = useAuthStore()
const themeStore = useThemeStore()
const searchQuery = ref('')
const router = useRouter()

const handlechangepassword = async () => {
  router.push('/auth/change-password/')
}


const handleLogout = async () => {
  await authStore.logout()
  window.location.href = '/login'
}
</script>

<template>
  <div class="user-bar">
    <el-input
      v-model="searchQuery"
      placeholder="全局搜索"
      clearable
      prefix-icon="Search"
      style="width: 280px;"
      size="small"
    />
    <div class="bar-right">
      <el-button link @click="handlechangepassword">{{ authStore.user?.username || 'admin' }}</el-button>
      <el-tooltip :content="themeStore.isDark ? '亮色模式' : '暗色模式'" placement="bottom">
        <el-button :icon="themeStore.isDark ? IconMoon : IconSun" size="small" @click="themeStore.toggleDark()" />
      </el-tooltip>
      <el-button link type="danger" size="small" @click="handleLogout">登出</el-button>
    </div>
  </div>
</template>

<style scoped>
.user-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  height: 42px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
  flex-shrink: 0;
}
.bar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.username {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
</style>
