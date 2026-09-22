import api from './index'

import type { PreferencePayload, UserPreferences } from '@/types'

/** 拉取当前用户的全部前端偏好（未登录不要调：401 会被拦截器当成登录失效跳 /login） */
export const getPreferences = () =>
  api.get<UserPreferences>('/api/me/preferences/').then((r) => r.data)

/** 按 key upsert 单条偏好；value 传 null 即删除该条 */
export const savePreference = (payload: PreferencePayload) =>
  api.put('/api/me/preferences/', payload).then((r) => r.data)

/** 按 key 删除偏好 */
export const deletePreference = (key: string) =>
  api.delete('/api/me/preferences/', { params: { key } }).then((r) => r.data)
