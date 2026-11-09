import 'vue-router'
import { Component } from 'vue'

declare module 'vue-router' {
  interface routeMeta {
    title?: string
    viewConfig?: {
      layout?: string
      keepAlive?: boolean
      permission?: string[]
      hiddenInMenu?: boolean
      [key: string]: any
    }
  }
}

export interface RouteConfig {
  name?: string
  path?: string
  component?: Component | (() => Promise<Component>)
  meta?: {
    title?: string
    viewConfig?: Record<string, any>
  }
}
