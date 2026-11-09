export interface DeviceInfo {
  name: string
  height: number
  model?: string
  vendor?: string
  ip?: string
}

export interface PositionInfo {
  position: string
  device: DeviceInfo
}

export interface RackInfo {
  name: string
  uCount: number
  detail: PositionInfo[]
}

export interface RackOptions {
  idc: []
  rowlist: []
  racklist: []
}
