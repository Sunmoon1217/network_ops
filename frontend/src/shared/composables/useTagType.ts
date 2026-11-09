export const useTagType = (map: Record<string, string>, fallback = 'info') => {
  return (value: string) => (map[value] || fallback) as any
}

// 常用预设
export const protocolTagType = useTagType({ static: 'warning', connected: 'success', ospf: 'primary', bgp: 'danger' })
export const modeTagType = useTagType({ layer3: 'primary', access: 'success', hybrid: 'warning', trunk: '' })
export const statusTagType = useTagType({ used: 'danger', reserved: 'warning', available: 'success' })
