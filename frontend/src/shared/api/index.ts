/**
 * 主站认证客户端：请求自动带 Token，401 清 token 并跳登录。
 * 大屏是免认证的独立应用，不要在 src/dashboard 里复用本实例
 * （见 src/dashboard/api/dashboard_api.ts 的独立 axios 实例）。
 */
import axios from 'axios'
import { getToken, removeToken } from '@/utils/token'

const api = axios.create({
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Token ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // 必须走 removeToken()，保证与 getToken() 使用同一个 localStorage key
      removeToken()
      // 已在登录页时不再跳转，避免整页刷新导致 /api/me/ 请求循环
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export default api
