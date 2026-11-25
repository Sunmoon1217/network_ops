import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './netops/App.vue'
import DashboardApp from './dashboard/App.vue'
import router from './netops/router'

import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import '@/assets/dark-tech.css'

// 两个入口共用本文件，按挂载点启动：index.html → #app（主站），dashboard.html → #dashboard（大屏）。
// 两个 app 各自建 pinia / router，只挂载命中的那个，避免互相改写 URL。
const netops = createApp(App)
const dashboard = createApp(DashboardApp)

if (document.querySelector('#app')) {
  netops.use(createPinia())
  netops.use(router)
  netops.mount('#app')
}

if (document.querySelector('#dashboard')) {
  dashboard.use(createPinia())
  dashboard.mount('#dashboard')
}
