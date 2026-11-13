import api from './index'

/** 软资产（T4）：只读接口，数据由后端 sync_soft_assets 归并产出。 */
export const getDomainAssets = (params?: Record<string, any>) =>
  api.get('/api/assets/domain-assets/', { params })

export const getDomainAsset = (id: number) =>
  api.get(`/api/assets/domain-assets/${id}/`)

export const getLoadBalancerServices = (params?: Record<string, any>) =>
  api.get('/api/assets/load-balancer-services/', { params })

export const getLoadBalancerService = (id: number) =>
  api.get(`/api/assets/load-balancer-services/${id}/`)
