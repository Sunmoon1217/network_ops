/**
 * Device type → SVG icon mapping for topology visualization.
 * Icons from Ansible networking-icons (Red Hat, MIT License).
 * Uses `currentColor` so icons inherit the color set in the SVG data URI.
 */

export const DEVICE_ICON_MAP: Record<string, string> = {
  firewall: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><g fill="currentColor"><rect x="88.8" y="162.7" width="48.7" height="18"/><rect x="148.4" y="162.7" width="48.7" height="18"/><rect x="148.4" y="104.5" width="48.7" height="18"/><rect x="58.9" y="133.5" width="48.7" height="18"/><rect x="118.6" y="133.5" width="48.7" height="18"/><path d="M128,0C57.3,0,0,57.3,0,128c0,70.7,57.3,128,128,128s128-57.3,128-128C256,57.3,198.7,0,128,0zM208,128c0,3-2.5,5.5-5.5,5.5h-24.3v18.2h24.3c3,0,5.5,2.5,5.5,5.5v28.9c0,3-2.5,5.5-5.5,5.5H83.3c-3,0-5.5-2.5-5.5-5.5v-23.7l-24.3,0c-3,0-5.5-2.5-5.5-5.5V128c0-3,2.5-5.5,5.5-5.5l24.3,0v-18.2H53.5c-3,0-5.5-2.5-5.5-5.5V69.9c0-3,2.5-5.5,5.5-5.5h119.2c3,0,5.5,2.5,5.5,5.5v23.7h24.3c3,0,5.5,2.5,5.5,5.5V128z"/><rect x="88.8" y="104.5" width="48.7" height="18"/><rect x="118.6" y="75.3" width="48.7" height="18"/><rect x="58.9" y="75.3" width="48.7" height="18"/></g></svg>`,

  switch: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><path fill="currentColor" d="M208.7,0H47.3C21.3,0,0,21.3,0,47.3v161.5c0,26,21.3,47.3,47.3,47.3h161.5c26,0,47.3-21.3,47.3-47.3V47.3C256,21.3,234.7,0,208.7,0zM113.8,64.3l57,0l-11.7-11.7c-2.3-2.3-2.3-6,0-8.2c2.3-2.3,6-2.3,8.2,0L188.9,66c1.1,1.1,1.7,2.6,1.7,4.1c0,1.5-0.6,3-1.7,4.1l-21.6,21.6c-2.3,2.3-6,2.3-8.2,0c-2.3-2.3-2.3-6,0-8.2l11.7-11.7h-57c-3.2,0-5.8-2.6-5.8-5.8C108,66.9,110.6,64.3,113.8,64.3zM51.1,108.7c0-1.5,0.6-3,1.7-4.1L74.4,83c2.3-2.3,6-2.3,8.2,0c2.3,2.3,2.3,6,0,8.2l-11.7,11.7h57c3.2,0,5.8,2.6,5.8,5.8c0,3.2-2.6,5.8-5.8,5.8l-57,0l11.7,11.7c2.3,2.3,2.3,6,0,8.2c-2.3,2.3-6,2.3-8.2,0l-21.6-21.6C51.7,111.7,51.1,110.2,51.1,108.7zM142.1,191.7l-57,0l11.7,11.7c2.3,2.3,2.3,6,0,8.2c-2.3,2.3-6,2.3-8.2,0L67,190c-1.1-1.1-1.7-2.6-1.7-4.1c0-1.5,0.6-3,1.7-4.1l21.6-21.6c2.3-2.3,6-2.3,8.2,0c2.3,2.3,2.3,6,0,8.2l-11.7,11.7h57c3.2,0,5.8,2.6,5.8,5.8C147.9,189.1,145.3,191.7,142.1,191.7zM203.2,151.4L181.6,173c-2.3,2.3-6,2.3-8.2,0c-2.3-2.3-2.3-6,0-8.2l11.7-11.7h-57c-3.2,0-5.8-2.6-5.8-5.8c0-3.2,2.6-5.8,5.8-5.8l57,0l-11.7-11.7c-2.3-2.3-2.3-6,0-8.2c2.3-2.3,6-2.3,8.2,0l21.6,21.6c1.1,1.1,1.7,2.6,1.7,4.1C204.9,148.8,204.3,150.3,203.2,151.4z"/></svg>`,

  router: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><path fill="currentColor" d="M128,0C57.3,0,0,57.3,0,128c0,70.7,57.3,128,128,128s128-57.3,128-128C256,57.3,198.7,0,128,0zM117.3,144.5l0,29.1c0,3.2-2.6,5.8-5.8,5.8c-3.2,0-5.8-2.6-5.8-5.8v0l0-15L74.2,190c-2.3,2.3-6,2.3-8.2,0c-1.1-1.1-1.7-2.6-1.7-4.1c0-1.5,0.6-3,1.7-4.2l31.5-31.5h-15c-3.2,0-5.8-2.6-5.8-5.8c0-3.2,2.6-5.8,5.8-5.8h29.1c1.5,0,3,0.7,4.1,1.8C116.7,141.4,117.3,142.9,117.3,144.5zM120,120c-2.3,2.3-6,2.3-8.2,0L75.6,83.9v16.5c0,3.2-2.6,5.8-5.8,5.8c-3.2,0-5.8-2.6-5.8-5.8l0-30.6c0-1.5,0.6-3,1.7-4.1c1.1-1.1,2.6-1.7,4.1-1.7l30.6,0c3.2,0,5.8,2.6,5.8,5.8s-2.6,5.8-5.8,5.8H83.9l36.2,36.2C122.3,114.1,122.3,117.8,120,120zM138.1,112.3l0-29.1c0-3.2,2.7-5.9,5.9-5.9c3.2,0,5.9,3,5.9,5.9h0.2v14.9L182,66c2.3-2.3,5.8-2.2,8,0c2.3,2.3,2.3,6,0,8.3l-32.1,32.2h15c3.2,0,5.8,2.5,5.8,5.7c0,3.2-2.6,5.8-5.8,5.8l-29.1,0c-1.5,0-3-0.6-4.1-1.7C138.7,115.2,138.1,113.8,138.1,112.3zM192,186.2c0,1.5-0.6,3-1.7,4.1c-1.1,1.1-2.6,1.7-4.1,1.7l-30.6,0c-3.2,0-5.8-2.6-5.8-5.8c0-3.2,2.6-5.8,5.8-5.8h16.5l-36.8-36.8c-1.1-1.1-1.7-2.6-1.7-4.1s0.6-3,1.7-4.1c2.3-2.3,6-2.3,8.2,0l36.8,36.8v-16.5c0-3.2,2.6-5.8,5.8-5.8c3.2,0,5.8,2.6,5.8,5.8V186.2z"/></svg>`,

  loadbalancer: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><g fill="currentColor"><circle cx="128.1" cy="182.4" r="7.3"/><circle cx="74.9" cy="182.4" r="7.3"/><circle cx="128.1" cy="73.6" r="7.3"/><circle cx="181.2" cy="182.4" r="7.3"/><path d="M218.5,37.5c-50-50-131-50-181,0c-50,50-50,131,0,181c50,50,131,50,181,0C268.5,168.5,268.5,87.5,218.5,37.5zM180.9,199.1c-9.3,0-17-7.5-17-16.7c0-7,5.2-13,10-15.5v-34.1c0-2.6-1.2-4.8-3.9-4.8h-35.6v38.9c6.3,2.5,10.5,8.5,10.5,15.5c0,9.2-7.5,16.7-16.8,16.7c-9.3,0-16.8-7.5-16.8-16.7c0-7,4.1-13,10.5-15.5V128H86.1c-2.6,0-3.9,2.2-3.9,4.8v34.1c4.7,2.5,10.1,8.5,10.1,15.5c0,9.2-7.9,16.7-17.1,16.7c-9.3,0-16.6-7.5-16.6-16.7c0-7,4.6-13,10.9-15.5v-34.1c0-9.6,6.9-17.4,16.5-17.4h35.6v-26c0-0.1,0-0.1,0-0.2c-6.1-2.5-10.5-8.5-10.5-15.5c0-9.2,7.5-16.7,16.8-16.7c9.3,0,16.8,7.5,16.8,16.7c0,7-4.3,13-10.5,15.5c0,0.1,0,0.1,0,0.2v26H170c9.7,0,16.5,7.8,16.5,17.4v34.1c6.3,2.5,10.8,8.5,10.8,15.5C197.4,191.6,190.2,199.1,180.9,199.1z"/></g></svg>`,

  server: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 236 79"><g fill="currentColor"><path d="M219.3,12.6c2.5,0,4.1,1.6,4.1,4.1v45.3c0,2.5-1.6,4.1-4.1,4.1H16.8c-2.5,0-4.1-1.6-4.1-4.1V16.8c0-2.5,1.6-4.1,4.1-4.1H219.3 M219.3,0H16.8C7.3,0,0,7.3,0,16.8v45.3c0,9.5,7.3,16.8,16.8,16.8h202.5c9.5,0,16.8-7.3,16.8-16.8V16.8C236.1,7.3,228.8,0,219.3,0L219.3,0z"/><path d="M51.5,33.4c3.1,0,5.3,2.2,5.3,5.3c0,3.1-2.2,5.3-5.3,5.3c-3.1,0-5.3-2.8-5.3-5.3C46.2,35.5,48.4,33.4,51.5,33.4 M51.5,20.7c-10.1,0-17.9,7.8-17.9,17.9c0,9.5,7.8,17.9,17.9,17.9c10.1,0,17.9-7.8,17.9-17.9C69.4,28.5,61.6,20.7,51.5,20.7L51.5,20.7z"/><circle cx="147.7" cy="29.7" r="5.6"/><circle cx="172.3" cy="29.7" r="5.6"/><circle cx="196.9" cy="29.7" r="5.6"/><circle cx="147.7" cy="49.3" r="5.6"/><circle cx="172.3" cy="49.3" r="5.6"/><circle cx="196.9" cy="49.3" r="5.6"/></g></svg>`,

  dns: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>`,

  wirelessac: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><line x1="12" y1="20" x2="12.01" y2="20"/></svg>`,

  internalac: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><rect x="10" y="11" width="4" height="4" rx="1"/><path d="M10 11v-1a2 2 0 0 1 4 0v1"/></svg>`,

  dwdm: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 22 12 12 22 2 12"/><line x1="12" y1="2" x2="12" y2="22"/><line x1="2" y1="12" x2="22" y2="12"/></svg>`,
}

/** Device type → color mapping */
export const DEVICE_COLOR_MAP: Record<string, string> = {
  firewall: '#f5222d',
  switch: '#1890ff',
  router: '#52c41a',
  loadbalancer: '#fa8c16',
  server: '#722ed1',
  dns: '#13c2c2',
  wirelessac: '#eb2f96',
  internalac: '#faad14',
  dwdm: '#2f54eb',
}

const DEFAULT_COLOR = '#8c8c8c'
const DEFAULT_ICON = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/></svg>`

/**
 * Return SVG string for a given device type.
 * The SVG uses `currentColor`, so set `color` in the data URI to control fill.
 */
export const getDeviceIconSvg = (deviceType: string): string => {
  return DEVICE_ICON_MAP[deviceType] ?? DEFAULT_ICON
}

export const getDeviceColor = (deviceType: string): string => {
  return DEVICE_COLOR_MAP[deviceType] ?? DEFAULT_COLOR
}

/** Build a data:image URI for use in G6 node style.iconSrc */
export const buildIconDataUri = (deviceType: string): string => {
  const color = getDeviceColor(deviceType)
  const svg = getDeviceIconSvg(deviceType).replace('currentColor', color)
  return `data:image/svg+xml,${encodeURIComponent(svg)}`
}
