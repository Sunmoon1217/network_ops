<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElConfigProvider } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { useAuthStore } from '@/stores/auth'
import AppNav from '@/ui/navigation/AppNav.vue'
import SideLayout from '@/layout/SideLayout.vue'
import Login from '@/views/login/Login.vue'

const route = useRoute()
const authStore = useAuthStore()

const isLoginPage = computed(() => route.path === '/login')
const isAuthenticated = computed(() => authStore.isAuthenticated)

onMounted(() => {
  if (authStore.isAuthenticated) authStore.fetchUser()
})
</script>

<template>
  <!-- 全局中文语言包：分页器、日期选择器、空数据等内置文案统一为中文 -->
  <el-config-provider :locale="zhCn">
    <Login v-if="isLoginPage" />
    <Login v-else-if="!isAuthenticated" />
    <SideLayout v-else>
      <template #nav><AppNav /></template>
      <template #main><router-view /></template>
    </SideLayout>
  </el-config-provider>
</template>

<style>
/* overscroll-behavior: none 关闭滚动触底回弹、滚动链与横向滑动触发的浏览器手势动画 */
* { margin: 0; padding: 0; box-sizing: border-box; overscroll-behavior: none; }
html, body, #app { height: 100%; width: 100%; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: var(--el-bg-color-page, #f5f7fa);
}
</style>
