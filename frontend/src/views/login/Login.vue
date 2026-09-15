<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { IconSun, IconMoon } from '@/ui/navigation/menu-icons'
import type { FormInstance, FormRules } from 'element-plus'

const router = useRouter()
const authStore = useAuthStore()
const themeStore = useThemeStore()
const formRef = ref<FormInstance | null>(null)
const loading = ref(false)

const formData = ref({ username: '', password: '' })

const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const handleLogin = async () => {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch { return }
  loading.value = true
  try {
    await authStore.login(formData.value.username, formData.value.password)
    router.push('/')
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.error || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-container">
    <div class="login-card">
      <el-button class="theme-toggle" :icon="themeStore.isDark ? IconMoon : IconSun" text circle @click="themeStore.toggleDark()" />

      <div class="login-header">
        <h1>网络运维管理平台</h1>
        <p>NetOps Management Console</p>
      </div>

      <el-form ref="formRef" :model="formData" :rules="rules" label-position="top" size="large" :disabled="loading" @keyup.enter="handleLogin">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="formData.username" placeholder="请输入用户名" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="formData.password" type="password" show-password placeholder="请输入密码" autocomplete="current-password" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" class="login-button" size="large" :loading="loading" @click="handleLogin">登 录</el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<style scoped>
.login-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: var(--el-bg-color-page);
}
.login-card {
  position: relative;
  width: 400px;
  padding: 40px 36px 32px;
  border-radius: 12px;
  background: var(--el-fill-color-blank);
  box-shadow: var(--el-box-shadow-light);
}
.theme-toggle {
  position: absolute;
  top: 12px;
  right: 12px;
}
.login-header {
  text-align: center;
  margin-bottom: 36px;
}
.login-header h1 {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.login-header p {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.login-button {
  width: 100%;
  margin-top: 8px;
}
</style>
