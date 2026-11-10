import api from './index'

import type {
  LoginResponse, UserInfo, RegisterPayload, ChangePasswordPayload,
} from '@/types'

export const login = (username: string, password: string) =>
  api.post<LoginResponse>('/api/auth/login/', { username, password }).then((r) => r.data)

/** 注册普通账号；成功即登录（后端直接回 token，响应体与 login 同形）。 */
export const register = (payload: RegisterPayload) =>
  api.post<LoginResponse>('/api/auth/register/', payload).then((r) => r.data)

export const changePassword = (payload: ChangePasswordPayload) =>
  api.put('/api/auth/change-password/', payload).then((r) => r.data)

export const logout = () => api.post('/api/auth/logout/')

export const getCurrentUser = () =>
  api.get<UserInfo>('/api/me/').then((r) => r.data)
