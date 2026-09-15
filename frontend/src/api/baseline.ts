import api from './index'

// SNMP
export const getSnmpConfigs = (params?: Record<string, any>) =>
  api.get('/api/assets/snmp-configs/', { params })

// 详情端点不受全局分页影响
export const getSnmpConfig = (id: number) =>
  api.get(`/api/assets/snmp-configs/${id}/`)

export const createSnmpConfig = (data: Record<string, any>) =>
  api.post('/api/assets/snmp-configs/', data)

export const updateSnmpConfig = (id: number, data: Record<string, any>) =>
  api.patch(`/api/assets/snmp-configs/${id}/`, data)

export const deleteSnmpConfig = (id: number) =>
  api.delete(`/api/assets/snmp-configs/${id}/`)

// NTP
export const getNtpConfigs = (params?: Record<string, any>) =>
  api.get('/api/assets/ntp-configs/', { params })

// 详情端点不受全局分页影响
export const getNtpConfig = (id: number) =>
  api.get(`/api/assets/ntp-configs/${id}/`)

export const createNtpConfig = (data: Record<string, any>) =>
  api.post('/api/assets/ntp-configs/', data)

export const updateNtpConfig = (id: number, data: Record<string, any>) =>
  api.patch(`/api/assets/ntp-configs/${id}/`, data)

export const deleteNtpConfig = (id: number) =>
  api.delete(`/api/assets/ntp-configs/${id}/`)

// Syslog
export const getSyslogConfigs = (params?: Record<string, any>) =>
  api.get('/api/assets/syslog-configs/', { params })

// 详情端点不受全局分页影响
export const getSyslogConfig = (id: number) =>
  api.get(`/api/assets/syslog-configs/${id}/`)

export const createSyslogConfig = (data: Record<string, any>) =>
  api.post('/api/assets/syslog-configs/', data)

export const updateSyslogConfig = (id: number, data: Record<string, any>) =>
  api.patch(`/api/assets/syslog-configs/${id}/`, data)

export const deleteSyslogConfig = (id: number) =>
  api.delete(`/api/assets/syslog-configs/${id}/`)
