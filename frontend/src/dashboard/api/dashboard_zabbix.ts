import ZabbixAPI from '@/api/zabbix_api'
import type {
  ZabbixTrigger,
  ZabbixConfig,
  ZabbixGroup,
  ZabbixHistoryPoint,
  ZabbixHost,
  ZabbixItem,
  ZabbixProblem,
} from '@/types'
import type { MessageApiInjection } from 'naive-ui/es/message/src/MessageProvider'

const HISTORY_VALUE_TYPES = ['0', '3'] as const

export interface ZabbixTagFilter {
  tag: string
  value: string
  operator?: number
}

export interface ThresholdStats {
  totalCount: number
  healthyCount: number
  abnormalCount: number
  healthyRate: number
}

export interface TimeAxisPoint {
  label: string
  timestamp: number
}

export const createZabbixApiFromEnv = async (
  env: Record<string, string | undefined>,
  message: MessageApiInjection,
) => {
  const config: ZabbixConfig = {
    url: env.VITE_ZABBIX_API_URL ? env.VITE_ZABBIX_API_URL : '',
    username: env.VITE_ZABBIX_USERNAME,
    password: env.VITE_ZABBIX_PASSWORD,
    token: env.VITE_ZABBIX_TOKEN,
  }

  const api = ZabbixAPI.create(config, message)
  return api
}

export const getGroupByName = async (api: ZabbixAPI, groupName: string) => {
  const groups = await api.callMethod<ZabbixGroup[]>('hostgroup.get', {
    output: ['groupid', 'name'],
    search: { name: [groupName] },
  })
  return groups ?? null
}

export const getHostCountByGroupName = async (api: ZabbixAPI, groupName: string) => {
  const groups = await getGroupByName(api, groupName)
  if (!groups) return null

  const hostCount = await api.callMethod<string>('host.get', {
    groupids: groups?.map((item) => item.groupid),
    countOutput: true,
  })

  const hostCountonline = await api.callMethod<string>('host.get', {
    groupids: groups?.map((item) => item.groupid),
    monitored_hosts: 1,
    countOutput: true,
  })

  return {
    groups,
    hostCount,
    hostCountonline,
  }
}

export const getHostsByGroupName = async (api: ZabbixAPI, groupName: string) => {
  const groups = await getGroupByName(api, groupName)
  if (!groups) return null

  const hosts = await api.callMethod<ZabbixHost[]>('host.get', {
    groupids: groups?.map((item) => item.groupid),
    output: ['hostid', 'host', 'name'],
  })

  return {
    groups,
    hosts,
  }
}

export const getItemsByGroupAndTag = async (
  api: ZabbixAPI,
  groupName: string,
  tagFilter: ZabbixTagFilter,
) => {
  const groups = await getGroupByName(api, groupName)
  if (!groups) return null

  const items = await api.callMethod<ZabbixItem[]>('item.get', {
    groupids: groups?.map((item) => item.groupid),
    output: ['itemid', 'value_type', 'name', 'key_'],
    tags: [
      {
        tag: tagFilter.tag,
        value: tagFilter.value,
        operator: tagFilter.operator ?? 1,
      },
    ],
    limit: 1,
    monitored: true,
    webitems: false,
  })

  return {
    groups,
    items,
  }
}

export const getItemsByNameAndHostid = async (
  api: ZabbixAPI,
  itemname: string[],
  hostsids: number[],
): Promise<ZabbixItem[]> => {
  const res = await api.callMethod<ZabbixItem[]>('item.get', {
    output: ['itemid', 'value_type', 'name', 'key_'],
    hostids: hostsids,
    search: {
      name: itemname,
    },
    monitored: true,
    webitems: false,
  })
  return res
}

export const getItemsByGroupName = async (api: ZabbixAPI, groupName: string) => {
  const groups = await getGroupByName(api, groupName)
  if (!groups) return null

  const itemsCPU = await api.callMethod<ZabbixItem[]>('item.get', {
    groupids: groups?.map((item) => item.groupid),
    output: ['itemid', 'value_type', 'name', 'key_', 'lastvalue', 'hostid'],
    selectHosts: ['hostid', 'host', 'name'],
    search: {
      key_: ['system.cpu.util'],
    },
    monitored: true,
    webitems: false,
  })

  const itemsMem = await api.callMethod<ZabbixItem[]>('item.get', {
    groupids: groups?.map((item) => item.groupid),
    output: ['itemid', 'value_type', 'name', 'key_', 'lastvalue', 'hostid'],
    selectHosts: ['hostid', 'host', 'name'],
    search: {
      key_: ['mem.usage'],
    },
    monitored: true,
    webitems: false,
  })
  return {
    itemsCPU,
    itemsMem,
  }
}

export const getPerformanceItemsByGroupName = async (api: ZabbixAPI, groupName: string) => {
  const groups = await getGroupByName(api, groupName)
  if (!groups) return null

  const itemsCPU = await api.callMethod<ZabbixItem[]>('item.get', {
    groupids: groups?.map((item) => item.groupid),
    output: ['itemid', 'value_type', 'name', 'key_', 'lastvalue', 'hostid'],
    selectHosts: ['hostid', 'host', 'name'],
    search: {
      // key_: ['system.cpu.util|cpu.usage1m.ratio|cpu.uilition.curr|zdns.cpu.usage|topsec.cpu'],
      name: ['CPU使用率'],
    },
    monitored: true,
    webitems: false,
  })

  const itemsMem = await api.callMethod<ZabbixItem[]>('item.get', {
    groupids: groups?.map((item) => item.groupid),
    output: ['itemid', 'value_type', 'name', 'key_', 'lastvalue', 'hostid'],
    selectHosts: ['hostid', 'host', 'name'],
    search: {
      // key_: ['mem.usage|mem.tmm.ratio|memory.util|ciscoMemUsage|topsec.mem|mem.uili'],
      name: ['内存使用率'],
    },
    monitored: true,
    webitems: false,
  })
  return {
    itemsCPU,
    itemsMem,
  }
}

export const getUnacknowledgedProblemCountByGroupName = async (
  api: ZabbixAPI,
  groupName: string,
) => {
  const groups = await getGroupByName(api, groupName)
  if (!groups) return null

  const problem = await api.callMethod<ZabbixProblem[]>('problem.get', {
    groupids: groups?.map((item) => item.groupid),
    object: 0,
    severities: [2, 3, 4, 5],
    suppressed: false,
    acknowledged: false,
  })
  const selectTriggers = await Promise.all(
    problem.map(async (item) => {
      const trigger = await api.callMethod<ZabbixTrigger[]>('trigger.get', {
        output: ['status', 'name'],
        triggerids: item.objectid,
        skipDependent: 1,
        filter: {
          status: '0',
          state: '0',
        },
      })
      return trigger
    }),
  )
  const triggerAcitve = selectTriggers.flat()

  return {
    groups,
    problemCount: triggerAcitve.length,
  }
}

export const getHistoryByItemid = async (
  api: ZabbixAPI,
  itemid: number,
  time_from: number,
): Promise<ZabbixHistoryPoint[]> => {
  const res = await api.callMethod<ZabbixHistoryPoint[]>('history.get', {
    output: ['itemid', 'value', 'clock'],
    history: 0,
    itemids: itemid,
    time_from: time_from,
    sortfield: 'clock',
    sortorder: 'DESC',
    limit: 100000,
  })
  return res
}

export const getRecentHistoryByItems = async (
  api: ZabbixAPI,
  items: ZabbixItem[],
  durationSeconds: number,
) => {
  if (!items.length) return []

  const now = Math.floor(Date.now() / 1000)
  const timeFrom = now - durationSeconds
  const itemIdsByType = HISTORY_VALUE_TYPES.map((historyType) => ({
    historyType,
    itemids: items.filter((item) => item.value_type === historyType).map((item) => item.itemid),
  }))

  const historyChunks = await Promise.all(
    itemIdsByType
      .filter((grouped) => grouped.itemids.length > 0)
      .map((grouped) =>
        api.callMethod<ZabbixHistoryPoint[]>('history.get', {
          output: ['itemid', 'value', 'clock'],
          history: Number(grouped.historyType),
          itemids: grouped.itemids,
          time_from: timeFrom,
          time_till: now,
          sortfield: 'clock',
          sortorder: 'DESC',
          limit: 100000,
        }),
      ),
  )

  return historyChunks.flat()
}

export const getItemsByHostnames = async (
  api: ZabbixAPI,
  hostnames: string[],
  itemNameKeyword?: string,
) => {
  if (!hostnames.length) return []

  const hosts = await api.callMethod<Array<{ hostid: string; host: string; name?: string }>>(
    'host.get',
    {
      output: ['hostid', 'host', 'name'],
      filter: { host: hostnames },
    },
  )

  if (!hosts.length) return []

  const hostMap = new Map(hosts.map((host) => [host.hostid, host]))
  const items = await api.callMethod<ZabbixItem[]>('item.get', {
    hostids: hosts.map((host) => host.hostid),
    output: ['itemid', 'value_type', 'name', 'key_', 'hostid'],
    selectHosts: ['hostid', 'host', 'name'],
    search: itemNameKeyword ? { name: itemNameKeyword } : undefined,
    searchWildcardsEnabled: !!itemNameKeyword,
    monitored: true,
    webitems: false,
  })

  const hostnameOrder = new Map(hostnames.map((hostname, index) => [hostname, index]))

  return items
    .filter((item) => {
      const host = item.hosts?.[0] ?? (item.hostid ? hostMap.get(item.hostid) : undefined)
      return !!host && hostnameOrder.has(host.host)
    })
    .sort((left, right) => {
      const leftHost =
        left.hosts?.[0]?.host ?? (left.hostid ? hostMap.get(left.hostid)?.host : '') ?? ''
      const rightHost =
        right.hosts?.[0]?.host ?? (right.hostid ? hostMap.get(right.hostid)?.host : '') ?? ''
      return (
        (hostnameOrder.get(leftHost) ?? Number.MAX_SAFE_INTEGER) -
        (hostnameOrder.get(rightHost) ?? Number.MAX_SAFE_INTEGER)
      )
    })
}

export const getItemsByGroupNameAndHostKeyword = async (
  api: ZabbixAPI,
  groupname: string,
  hostname: string,
  itemKeywords: string[],
) => {
  const hostResult = await getHostsByGroupName(api, groupname)
  if (!hostResult) return null

  const matchedHosts = hostResult.hosts.filter((host) => host.name?.includes(hostname))
  if (!matchedHosts.length) {
    return {
      group: hostResult.groups,
      hosts: [],
      items: [],
    }
  }
  const items = await api.callMethod<ZabbixItem[]>('item.get', {
    hostids: matchedHosts.map((host) => host.hostid),
    output: ['itemid', 'value_type', 'name', 'key_', 'lastvalue', 'hostid'],
    selectHosts: ['hostid', 'host', 'name'],
    search: {
      name: '接口管理状态',
    },
    monitored: true,
    webitems: false,
  })

  return {
    group: hostResult.groups,
    hosts: matchedHosts,
    items,
  }
}

export const buildRecentTimeAxis = (
  durationMinutes: number,
  stepMinutes: number,
): TimeAxisPoint[] => {
  const pointCount = Math.floor(durationMinutes / stepMinutes)
  const now = new Date()

  // 将当前时间对齐到最近的 stepMinutes 倍数（向下取整）
  const minutes = now.getMinutes()
  const roundedMinutes = minutes - (minutes % stepMinutes)
  const roundedNow = new Date(now.getTime())

  roundedNow.setSeconds(0, 0) // 清除秒和毫秒
  roundedNow.setMinutes(roundedMinutes) // 对齐到最近的 stepMinutes 倍数

  // 时间轴起点：从 roundedNow - durationMinutes 开始
  const startTime = new Date(roundedNow.getTime() - (pointCount - 1) * stepMinutes * 60 * 1000)

  return Array.from({ length: pointCount }, (_, index) => {
    const pointTime = new Date(startTime.getTime() + index * stepMinutes * 60 * 1000)
    return {
      label: `${pointTime.getHours().toString().padStart(2, '0')}:${pointTime.getMinutes().toString().padStart(2, '0')}`,
      timestamp: Math.floor(pointTime.getTime() / 1000),
    }
  })
}

export const buildSeriesValuesFromHistory = (
  itemId: string,
  historyPoints: ZabbixHistoryPoint[],
  timeAxis: TimeAxisPoint[],
  stepMinutes: number,
) => {
  const sortedPoints = historyPoints
    .filter((point) => point.itemid === itemId)
    .map((point) => ({
      ...point,
      clockNum: Number(point.clock),
      valueNum: Number(point.value),
    }))
    .filter((point) => !Number.isNaN(point.clockNum) && !Number.isNaN(point.valueNum))
    .sort((left, right) => left.clockNum - right.clockNum)

  const stepSeconds = stepMinutes * 60

  return timeAxis.map((axisPoint) => {
    const bucketStart = axisPoint.timestamp - stepSeconds
    const bucketValues = sortedPoints
      .filter((point) => point.clockNum > bucketStart && point.clockNum <= axisPoint.timestamp)
      .map((point) => point.valueNum)

    if (!bucketValues.length) return 0

    const average = bucketValues.reduce((sum, value) => sum + value, 0) / bucketValues.length
    return Number(average.toFixed(1))
  })
}

export const normalizePercent = (value: number) => {
  if (Number.isNaN(value)) return 0
  return Math.max(0, Math.min(100, Number(value.toFixed(1))))
}

export const filterItemsByKeywords = (items: ZabbixItem[], keywords: string[]) => {
  const normalizedKeywords = keywords.map((keyword) => keyword.toLowerCase())
  return items.filter((item) => {
    const candidate = `${item.name ?? ''} ${item.key_ ?? ''}`.toLowerCase()
    return normalizedKeywords.some((keyword) => candidate.includes(keyword))
  })
}

export const buildTopListFromItems = (items: ZabbixItem[], topN = 5) =>
  items
    .map((item) => {
      const value = Number(item.lastvalue)
      const host = item.hosts![0]
      return {
        label: host.name ?? host.host ?? item.name ?? item.itemid,
        value: normalizePercent(Number.isNaN(value) ? 0 : value),
      }
    })
    .sort((left, right) => right.value - left.value)
    .slice(0, topN)

export const getMaxValueFromItems = (items: ZabbixItem[]) => {
  const values = items
    .map((item) => Number(item.lastvalue))
    .filter((value) => !Number.isNaN(value))
    .map((value) => normalizePercent(value))

  return values.length ? Math.max(...values) : 0
}

export const calculateUpRatioFromItems = (items: ZabbixItem[]) => {
  const validValues = items
    .map((item) => Number(item.lastvalue))
    .filter((value) => !Number.isNaN(value))

  if (!validValues.length) {
    return {
      totalCount: 0,
      upCount: 0,
      ratio: 0,
    }
  }

  const upCount = validValues.filter((value) => value === 1).length
  return {
    totalCount: validValues.length,
    upCount,
    ratio: normalizePercent((upCount / validValues.length) * 100),
  }
}

export const calculateThresholdStats = (
  points: ZabbixHistoryPoint[],
  threshold: number,
): ThresholdStats => {
  let healthyCount = 0
  let abnormalCount = 0

  for (const point of points) {
    const currentValue = Number(point?.value)
    if (Number.isNaN(currentValue)) continue

    if (currentValue <= threshold) {
      healthyCount += 1
    } else {
      abnormalCount += 1
    }
  }

  const totalCount = healthyCount + abnormalCount
  return {
    totalCount,
    healthyCount,
    abnormalCount,
    healthyRate: totalCount ? (healthyCount / totalCount) * 100 : 0,
  }
}
