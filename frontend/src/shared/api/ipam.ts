import api from './index'

// 标签
export const getTags = (params?: Record<string, any>) =>
  api.get('/api/assets/tags/', { params })

// 详情端点不受全局分页影响
export const getTag = (id: number) =>
  api.get(`/api/assets/tags/${id}/`)

export const createTag = (data: Record<string, any>) =>
  api.post('/api/assets/tags/', data)

export const updateTag = (id: number, data: Record<string, any>) =>
  api.patch(`/api/assets/tags/${id}/`, data)

export const deleteTag = (id: number) =>
  api.delete(`/api/assets/tags/${id}/`)

// 网段
export const getSubnets = (params?: Record<string, any>) =>
  api.get('/api/assets/subnets/', { params })

// 详情端点不受全局分页影响
export const getSubnet = (id: number) =>
  api.get(`/api/assets/subnets/${id}/`)

export const createSubnet = (data: Record<string, any>) =>
  api.post('/api/assets/subnets/', data)

export const updateSubnet = (id: number, data: Record<string, any>) =>
  api.patch(`/api/assets/subnets/${id}/`, data)

export const deleteSubnet = (id: number) =>
  api.delete(`/api/assets/subnets/${id}/`)

// IP 地址
export const getIpAddresses = (params?: Record<string, any>) =>
  api.get('/api/assets/ip-addresses/', { params })

// 详情端点不受全局分页影响
export const getIpAddress = (id: number) =>
  api.get(`/api/assets/ip-addresses/${id}/`)

export const createIpAddress = (data: Record<string, any>) =>
  api.post('/api/assets/ip-addresses/', data)

export const updateIpAddress = (id: number, data: Record<string, any>) =>
  api.patch(`/api/assets/ip-addresses/${id}/`, data)

export const deleteIpAddress = (id: number) =>
  api.delete(`/api/assets/ip-addresses/${id}/`)
