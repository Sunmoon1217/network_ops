import axios, { AxiosError, type AxiosResponse } from 'axios'
import type { DashboardData, RackInfo, Response, RackOptions } from '@/types'
// 创建axios实例
const api = axios.create({
  // 根据环境变量设置基础URL
  baseURL: import.meta.env.VITE_DASHBOARD_URL || 'http://localhost:8000/dashboard',
  timeout: 10000, // 请求超时时间
  headers: {
    'Content-Type': 'application/json',
  },
})

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    // 可以在这里添加认证token等
    // const token = localStorage.getItem('token')
    // if (token) {
    //   config.headers.Authorization = `Bearer ${token}`
    // }
    return config
  },
  (error) => {
    return Promise.reject(error)
  },
)

// 响应拦截器
api.interceptors.response.use(
  (response: AxiosResponse<Response>) => {
    // 统一处理响应数据
    const res = response.data
    return res.result
  },
  (error: AxiosError) => {
    // 统一处理错误
    console.error('API请求错误:', error)
    if (error.response) {
      // 服务器返回错误状态码
      console.error('错误状态码:', error.response.status)
      console.error('错误数据:', error.response.data)
    } else if (error.request) {
      // 请求已发送但没有收到响应
      console.error('未收到响应:', error.request)
    } else {
      // 请求配置出错
      console.error('请求配置错误:', error.message)
    }
    return Promise.reject(error)
  },
)

// API 方法定义
export const getDevices = () => api.get('/devices/')
export const getDeviceById = (id: number) => api.get(`/devices/${id}/`)
export const createDevice = (data: any) => api.post('/devices/', data)
export const updateDevice = (id: number, data: any) => api.put(`/devices/${id}/`, data)
export const deleteDevice = (id: number) => api.delete(`/devices/${id}/`)

export const getdashboard = (panel: string, group: string): Promise<DashboardData[]> =>
  api.get('/', { params: { panel: panel, group: group } })

export const getlinklatest = (time: string): Promise<DashboardData[]> =>
  api.get('/', { params: { panel: 'link', group: 'statistic', name: `bandwidth-${time}` } })

export const getidc = (): Promise<[]> => api.get('/cabinets/idc')

export const getracklist = (idc?: string): Promise<[]> =>
  api.get('/cabinets/racklist', { params: { idc: idc } })

export const getrack = (idc: string, rack_id: string): Promise<RackInfo[]> =>
  api.get('/cabinets', { params: { idc: idc, rack_id: rack_id } })

export default api
