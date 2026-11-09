import type {
  ZabbixHistoryPoint,
  TimeValuePoint,
  InterfaceMaxData,
  ZabbixItem,
} from '@/types/zabbixapi'

export const processToPoint = (
  rawData: ZabbixHistoryPoint[],
  timeAxis: number[],
  stepMinutes: number,
): number[] => {
  const timeAxisLength = timeAxis.length
  let intervals = timeAxis.map((point) => {
    const start = point - stepMinutes * 60
    const end = point
    return { start, end }
  })
  const sums: number[] = new Array(timeAxisLength).fill(0)
  const counts: number[] = new Array(timeAxisLength).fill(0)

  for (const data of rawData) {
    const clock = Number(data.clock)
    for (let i = 0; i < intervals.length; i++) {
      const interval = intervals[i]
      if (clock >= interval.start && clock < interval.end) {
        sums[i] += Number(data.value)
        counts[i] += 1
      }
    }
  }

  return sums.map((sum, i) => {
    if (counts[i] === 0) {
      return -1
    }
    return sum / counts[i]
  })
}

export const mergeMax = <T extends number>(...arrays: T[][]): T[] => {
  const length = arrays[0].length
  if (length === 0) return []
  if (arrays.length === 1) return arrays[0]

  return arrays[0].map((_, i) => {
    const values = arrays.map((arr) => arr[i])
    return Math.max(...values) as T
  })
}

export const appendAndTrim = (
  existingTime: number[],
  existingData: number[],
  newTime: number,
  newData: number,
) => {
  if (existingTime.includes(newTime)) {
    return { TimeList: existingTime, maxData: existingData }
  }
  const timeList = [...existingTime, newTime].sort((a, b) => a - b)
  const maxData = [...existingData, newData]

  const nowTs = Math.floor(Date.now() / 1000)
  const keepFrom = nowTs - 10800
  const keepIndex = timeList.findIndex((t) => keepFrom)
  if (keepIndex === -1) return { timeList, maxData }
  return {
    timeList: timeList.slice(keepIndex),
    maxData: maxData.slice(keepIndex),
  }
}

export const isZabbixItem = (data: unknown): data is ZabbixItem => {
  return typeof data === 'object' && data !== null && 'itemid' in data && 'value_type' in data
}
