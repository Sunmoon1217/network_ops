import api from './index'

// 设备
export const getDevices = (params?: Record<string, any>) =>
  api.get('/api/assets/devices/', { params })

export const getDevice = (id: number) =>
  api.get(`/api/assets/devices/${id}/`)

// 设备配置
export const getDeviceConfigs = (params?: Record<string, any>) =>
  api.get('/api/assets/device-configs/', { params })

// 导入
export const importDevices = (file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/api/assets/import-devices/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  })
}

// Git 配置
export const getGitConfigContent = (hostname: string, commitHash: string) =>
  api.get('/api/configs/git-content/', { params: { hostname, commit_hash: commitHash } })

export const getGitDiff = (hostname: string, oldHash: string, newHash: string) =>
  api.get('/api/configs/git-diff/', { params: { hostname, old_hash: oldHash, new_hash: newHash } })

export const getConfigHistory = (hostname: string, limit = 20) =>
  api.get('/api/configs/history/', { params: { hostname, limit } })

// DCIM
export const getDatacenters = (params?: Record<string, any>) =>
  api.get('/api/assets/datacenters/', { params })

export const getRooms = (params?: Record<string, any>) =>
  api.get('/api/assets/rooms/', { params })

export const getCabinets = (params?: Record<string, any>) =>
  api.get('/api/assets/cabinets/', { params })
