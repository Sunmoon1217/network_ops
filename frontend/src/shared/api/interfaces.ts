import api from './index'

// 接口
export const getInterfaces = (params?: Record<string, any>) =>
  api.get('/api/assets/interfaces/', { params })

export const getInterface = (id: number) =>
  api.get(`/api/assets/interfaces/${id}/`)

export const updateInterface = (id: number, data: Record<string, any>) =>
  api.patch(`/api/assets/interfaces/${id}/`, data)

// VRF
export const getVrfs = (params?: Record<string, any>) =>
  api.get('/api/assets/vrfs/', { params })

// VLAN
export const getVlans = (params?: Record<string, any>) =>
  api.get('/api/assets/vlans/', { params })
