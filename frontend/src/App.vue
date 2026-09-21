<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElConfigProvider } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { useAuthStore } from '@/stores/auth'
import AppNav from '@/layout/AppNav.vue'
import SideLayout from '@/layout/SideLayout.vue'
import Login from '@/views/login/Login.vue'

const route = useRoute()
const authStore = useAuthStore()

const location = ref(zhCn)

// 公开页（登录 / 注册）由路由的 meta.skipLayout 标记，直接交给 router-view 渲染；
// 不能只判断「未登录」——那样任何公开页都会被渲染成 Login（注册页就这么被吞掉过）。
const isPublicPage = computed(() => route.meta.skipLayout === true)
const isAuthenticated = computed(() => authStore.isAuthenticated)

onMounted(() => {
  if (authStore.isAuthenticated) authStore.fetchUser()
})
</script>

<template>
  <!-- 全局中文语言包：分页器、日期选择器、空数据等内置文案统一为中文 -->
  <el-config-provider :locale="location">
    <router-view v-if="isPublicPage" />
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
