import api from './index'

export interface LoginResponse {
  token: string
  user: { id: number; username: string }
}

export interface UserInfo {
  id: number
  username: string
  email?: string
  is_staff?: boolean
  phone?: string
  avatar?: string
}

export interface RegisterPayload {
  username: string
  password: string
  email?: string
  phone?: string
}

export interface ChangePasswordPayload {
  old_password: string
  new_password: string
  confirm_password: string
}

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
