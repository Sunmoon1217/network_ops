import api from './index'

export const getTopologies = (params?: any) => api.get('/api/assets/topologies/', { params })
export const getTopology = (id: number) => api.get(`/api/assets/topologies/${id}/`)
export const createTopology = (data: any) => api.post('/api/assets/topologies/', data)
export const updateTopology = (id: number, data: any) => api.patch(`/api/assets/topologies/${id}/`, data)
export const deleteTopology = (id: number) => api.delete(`/api/assets/topologies/${id}/`)
