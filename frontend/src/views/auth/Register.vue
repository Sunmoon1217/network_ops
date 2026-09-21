<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { IconSun, IconMoon } from '@/assets/menu-icons'
import type { FormInstance, FormRules } from 'element-plus'

const router = useRouter()
const authStore = useAuthStore()
const themeStore = useThemeStore()
const formRef = ref<FormInstance | null>(null)
const loading = ref(false)

const formData = ref({ username: '', email: '', phone: '', password: '', confirm: '' })

const rules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 150, message: '用户名长度 3–150 个字符', trigger: 'blur' },
  ],
  // 邮箱与手机号都是可选的：留空就不校验（后端也不强制）
  email: [{ type: 'email', message: '邮箱格式不正确', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 8, message: '密码至少 8 位', trigger: 'blur' },
  ],
  confirm: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value !== formData.value.password) callback(new Error('两次输入的密码不一致'))
        else callback()
      },
      trigger: 'blur',
    },
  ],
}

/** 后端返回的是 DRF 的字段错误（如 {"username": ["该用户名已被占用"]}），取第一条给人看。 */
const firstErrorMessage = (error: any, fallback: string): string => {
  const data = error?.response?.data
  if (!data || typeof data !== 'object') return fallback
  if (typeof data.error === 'string') return data.error
  if (typeof data.detail === 'string') return data.detail
  for (const value of Object.values(data)) {
    if (Array.isArray(value) && value.length) return String(value[0])
    if (typeof value === 'string' && value) return value
  }
  return fallback
}

const handleRegister = async () => {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch { return }
  loading.value = true
  try {
    // 后端只创建普通账号（is_staff / is_superuser 由服务端决定，前端传不了）
    await authStore.register({
      username: formData.value.username,
      password: formData.value.password,
      email: formData.value.email,
      phone: formData.value.phone,
    })
    ElMessage.success('注册成功，已自动登录')
    router.push('/')
  } catch (error: any) {
    ElMessage.error(firstErrorMessage(error, '注册失败'))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="register-container">
    <div class="register-card">
      <el-button class="theme-toggle" :icon="themeStore.isDark ? IconMoon : IconSun" text circle @click="themeStore.toggleDark()" />

      <div class="register-header">
        <h1>注册账号</h1>
        <p>NetOps Management Console</p>
      </div>

      <el-form ref="formRef" :model="formData" :rules="rules" label-position="top" size="large" :disabled="loading" @keyup.enter="handleRegister">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="formData.username" placeholder="字母、数字与 @ . + - _" autocomplete="username" />
        </el-form-item>
        <el-form-item label="邮箱（可选）" prop="email">
          <el-input v-model="formData.email" placeholder="用于接收通知" autocomplete="email" />
        </el-form-item>
        <el-form-item label="手机号（可选）" prop="phone">
          <el-input v-model="formData.phone" maxlength="20" placeholder="联系电话" autocomplete="tel" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="formData.password" type="password" show-password placeholder="至少 8 位，不能是纯数字或与用户名相似" autocomplete="new-password" />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirm">
          <el-input v-model="formData.confirm" type="password" show-password placeholder="请再次输入密码" autocomplete="new-password" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" class="register-button" size="large" :loading="loading" @click="handleRegister">注 册</el-button>
        </el-form-item>
      </el-form>

      <div class="register-footer">
        <span>已经有账号了？</span>
        <el-link type="primary" underline="never" @click="router.push('/login')">返回登录</el-link>
      </div>
    </div>
  </div>
</template>

<style scoped>
.register-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: var(--el-bg-color-page);
}
.register-card {
  position: relative;
  width: 400px;
  padding: 40px 36px 28px;
  border-radius: 12px;
  background: var(--el-fill-color-blank);
  box-shadow: var(--el-box-shadow-light);
}
.theme-toggle {
  position: absolute;
  top: 12px;
  right: 12px;
}
.register-header {
  text-align: center;
  margin-bottom: 28px;
}
.register-header h1 {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.register-header p {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.register-button {
  width: 100%;
  margin-top: 8px;
}
.register-footer {
  margin-top: 4px;
  text-align: center;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
</style>
