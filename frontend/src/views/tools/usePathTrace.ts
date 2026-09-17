import { ref } from 'vue'
import api from '@/api/index'

export interface HopData {
  device_name: string
  device_id: number
  device_type: string
  zone: string
  vrf: string
  matched_policy: any
  matched_nat: any
  matched_route: any
  matched_vs: any
  action: string
  src_before: string
  src_after: string
  dst_before: string
  dst_after: string
  port_before: string
  port_after: string
}

export interface TraceResult {
  hops: HopData[]
  final_src: string
  final_dst: string
  final_port: string
  blocked: boolean
  blocked_by: string
  lb_backend: any[]
  error: string
}

export const actionColor: Record<string, string> = { allow: '#18a058', deny: '#d03050' }
export const actionLabel: Record<string, string> = { allow: '放行', deny: '拒绝' }
export const deviceLabel: Record<string, string> = {
  firewall: '防火墙',
  switch: '交换机',
  slb: '服务器负载均衡',
  gslb: '全局负载均衡',
}

export const hasTranslation = (hop: HopData): boolean => {
  return !!(hop.src_after || hop.dst_after || hop.port_after)
}

export const usePathTrace = () => {
  const srcIp = ref('')
  const dstIp = ref('')
  const dstPort = ref('')
  const loading = ref(false)
  const result = ref<TraceResult | null>(null)
  const error = ref('')

  const handleTrace = async () => {
    if (!srcIp.value || !dstIp.value) {
      error.value = '请输入源地址和目的地址'
      return
    }
    loading.value = true
    error.value = ''
    result.value = null
    try {
      const resp = await api.get('/api/trace/', {
        params: { src: srcIp.value, dst: dstIp.value, port: dstPort.value },
      })
      result.value = resp.data
      if (result.value?.error) {
        error.value = result.value.error
      }
    } catch (e: any) {
      error.value = e.response?.data?.error || '请求失败'
    } finally {
      loading.value = false
    }
  }

  return { srcIp, dstIp, dstPort, loading, result, error, handleTrace }
}
