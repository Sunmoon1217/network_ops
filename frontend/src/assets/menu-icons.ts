import { h, type Component } from 'vue'

const createIcon = (svg: string): Component => {
  return {
    render() {
      return h('svg', {
        viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor',
        'stroke-width': '1.8', 'stroke-linecap': 'round', 'stroke-linejoin': 'round',
        style: { width: '1em', height: '1em' },
        innerHTML: svg,
      })
    },
  }
}

export const IconOverview = createIcon('<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>')
export const IconDevices = createIcon('<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="7" cy="12" r="1.5" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none"/><circle cx="17" cy="12" r="1.5" fill="currentColor" stroke="none"/><line x1="6" y1="18" x2="6" y2="21"/><line x1="12" y1="18" x2="12" y2="21"/><line x1="18" y1="18" x2="18" y2="21"/>')
export const IconDeviceList = createIcon('<rect x="4" y="2" width="16" height="5" rx="1"/><rect x="4" y="9.5" width="16" height="5" rx="1"/><circle cx="7" cy="4.5" r="0.8" fill="currentColor" stroke="none"/><circle cx="7" cy="12" r="0.8" fill="currentColor" stroke="none"/>')
export const IconBaseline = createIcon('<path d="M12 2l8 4v5c0 5.25-3.5 9.74-8 11-4.5-1.26-8-5.75-8-11V6l8-4z"/><polyline points="9 12 11 14 15 10"/>')
export const IconInterfaces = createIcon('<path d="M6 2h12a2 2 0 012 2v16a2 2 0 01-2 2H6a2 2 0 01-2-2V4a2 2 0 012-2z"/><path d="M8 6h8v4H8z"/><line x1="9" y1="14" x2="9" y2="18"/><line x1="11" y1="14" x2="11" y2="18"/><line x1="13" y1="14" x2="13" y2="18"/><line x1="15" y1="14" x2="15" y2="18"/><path d="M10 2l2 4 2-4"/>')
export const IconParsers = createIcon('<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/><line x1="14" y1="4" x2="10" y2="20"/>')
export const IconConfig = createIcon('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>')
export const IconLoadBalancer = createIcon('<line x1="12" y1="3" x2="12" y2="21"/><line x1="4" y1="7" x2="20" y2="7"/><path d="M4 7l-2 7h6L4 7z"/><path d="M20 7l-2 7h6L20 7z"/><line x1="4" y1="14" x2="8" y2="14"/><line x1="16" y1="14" x2="20" y2="14"/>')
export const IconDns = createIcon('<circle cx="12" cy="12" r="10"/><ellipse cx="12" cy="12" rx="4" ry="10"/><line x1="2" y1="12" x2="22" y2="12"/>')
export const IconPolicy = createIcon('<path d="M12 2l8 4v5c0 5.25-3.5 9.74-8 11-4.5-1.26-8-5.75-8-11V6l8-4z"/><line x1="9" y1="12" x2="15" y2="12"/><line x1="12" y1="9" x2="12" y2="15"/>')
export const IconIp = createIcon('<circle cx="12" cy="12" r="10"/><ellipse cx="12" cy="12" rx="4" ry="10"/><line x1="2" y1="12" x2="22" y2="12"/>')
export const IconSubnet = createIcon('<polygon points="12 2 22 8 12 14 2 8"/><polyline points="2 12 12 18 22 12"/><polyline points="2 16 12 22 22 16"/>')
export const IconLayoutTop = createIcon('<rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/>')
export const IconLayoutSide = createIcon('<rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/>')

export const IconSun = createIcon('<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>')

export const IconMoon = createIcon('<path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>')

export const IconTools = createIcon('<path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/>')

export const IconPathTrace = createIcon('<polygon points="3 11 22 2 13 21 11 13 3 11"/>')

export const IconRouting = createIcon('<polygon points="3 11 22 2 13 21 11 13 3 11"/>')
