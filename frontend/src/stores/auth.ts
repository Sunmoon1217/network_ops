import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as apiLogin, logout as apiLogout, getCurrentUser, register as apiRegister, changePassword as apichangesecert } from '@/api/auth'
import { getToken, setToken, removeToken } from '@/utils/token'

import type { UserInfo } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(getToken())
  const user = ref<UserInfo | null>(null)
  const loading = ref(false)

  const isAuthenticated = computed(() => !!token.value)

  const login = async (username: string, password: string) => {
    loading.value = true
    try {
      const data = await apiLogin(username, password)
      token.value = data.token
      setToken(data.token)
      user.value = data.user
      return true
    } finally {
      loading.value = false
    }
  }

  /** 注册：成功后与 login 一样把 token / 用户写进 store，前端不必再登录一次。 */
  const register = async (payload: { username: string; password: string; email?: string; phone?: string }) => {
    loading.value = true
    try {
      const data = await apiRegister(payload)
      token.value = data.token
      setToken(data.token)
      user.value = data.user
      return true
    } finally {
      loading.value = false
    }
  }

  const logout = async () => {
    try {
      if (token.value) await apiLogout()
    } finally {
      token.value = null
      user.value = null
      removeToken()
    }
  }

  const fetchUser = async () => {
    if (!token.value) return
    try {
      user.value = await getCurrentUser()
    } catch {
      token.value = null
      user.value = null
      removeToken()
    }
  }

  const changePassword = async (from: any) => {
    if (!token.value) return
    try {
      await apichangesecert(from)
      // const result = await apichangesecert(from)
      // console.log("api返回结果", result)
      return true
    } catch {
      return false
    }
  }

  return { token, user, loading, isAuthenticated, login, register, logout, fetchUser, changePassword }
})
