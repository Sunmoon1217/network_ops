import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import DashboardApp from './dashboard/App.vue'
import router from './router'

import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import '@/assets/dark-tech.css'

// 两个应用共用同一个启动文件，按页面里的挂载点各自启动：
//   index.html     → #app       → netops（原有 SPA，路由 / 鉴权都在 App.vue 与 router 里）
//   dashboard.html → #dashboard → dashboard（待合并的 dashboard 项目落点）
// 两个 app 都先建好，但只给命中的那个装插件并挂载：vue-router 在 use 时就接管 history，
// 两个页面各自启动一套才不会互相改写 URL；pinia 也各自独立，不共享状态。
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
