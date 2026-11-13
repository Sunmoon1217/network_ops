import { createRouter, createWebHistory, type RouteLocationGeneric } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getToken } from '@/utils/token'
import { useAuthStore } from '@netops/stores/auth'

// 带参数的旧路径重定向：把匹配到的参数拼进新路径
const legacyRedirect = (build: (to: RouteLocationGeneric) => string) => (to: RouteLocationGeneric) => build(to)

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/register',
      name: 'register',
      component: () => import('@netops/views/auth/Register.vue'),
      meta: { skipLayout: true },
    },
    {
      path: '/auth/change-password',
      name: 'change-password',
      component: () => import('@netops/views/auth/ChangePassword.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/',
      name: 'home',
      component: () => import('@netops/views/Home.vue'),
      meta: { requiresAuth: true },
    },
    {
      // 资产域（对应导航「资产」分组）。前缀用 /asset 而不是 /assets：
      // /assets/* 是 Vite 构建产物保留前缀（Django 的 serve_frontend_assets 与
      // nginx 的 location /assets/ 都会先吃掉它），刷新必 404。
      path: '/asset',
      meta: { requiresAuth: true },
      children: [
        { path: '', redirect: '/asset/devices' },
        // 主机 / 网络设备
        { path: 'devices', name: 'asset-device-list', component: () => import('@netops/views/devices/list.vue'), meta: { keepAlive: true } },
        { path: 'devices/create', name: 'asset-device-create', component: () => import('@netops/views/devices/forms/DeviceForm.vue'), meta: { requiresOperator: true } },
        { path: 'devices/:id/edit', name: 'asset-device-edit', component: () => import('@netops/views/devices/forms/DeviceForm.vue'), meta: { requiresOperator: true } },
        { path: 'devices/:id/config', name: 'asset-device-config', component: () => import('@netops/views/devices/config.vue') },
        { path: 'devices/:id/history', name: 'asset-device-history', component: () => import('@netops/views/devices/history.vue') },
        { path: 'devices/:id/compare', name: 'asset-device-compare', component: () => import('@netops/views/devices/compare.vue') },
        // 组件：网卡/接口、VLAN
        { path: 'interfaces', name: 'asset-interface-list', component: () => import('@netops/views/devices/interfaces.vue') },
        { path: 'interfaces/:id/edit', name: 'asset-interface-edit', component: () => import('@netops/views/devices/forms/InterfaceForm.vue'), meta: { requiresOperator: true } },
        { path: 'vlans', name: 'asset-vlans', component: () => import('@netops/views/devices/vlans.vue') },
        // 网络服务：IP 地址、网段（ipam 视图搬进资产前缀）
        { path: 'ip-addresses', name: 'asset-ip-addresses', component: () => import('@netops/views/ipam/ip-address.vue') },
        { path: 'ip-addresses/create', name: 'asset-ip-create', component: () => import('@netops/views/ipam/forms/IpAddressForm.vue'), meta: { requiresOperator: true } },
        { path: 'ip-addresses/:id/edit', name: 'asset-ip-edit', component: () => import('@netops/views/ipam/forms/IpAddressForm.vue'), meta: { requiresOperator: true } },
        { path: 'subnets', name: 'asset-subnets', component: () => import('@netops/views/ipam/index.vue') },
        { path: 'subnets/create', name: 'asset-subnet-create', component: () => import('@netops/views/ipam/forms/SubnetForm.vue'), meta: { requiresOperator: true } },
        { path: 'subnets/:id/edit', name: 'asset-subnet-edit', component: () => import('@netops/views/ipam/forms/SubnetForm.vue'), meta: { requiresOperator: true } },
        { path: 'load-balancer', name: 'asset-load-balancer', component: () => import('@netops/views/asset/load-balancer.vue'), meta: { title: '负载均衡（资产）' } },
        { path: 'domain', name: 'asset-domain', component: () => import('@netops/views/asset/domain.vue'), meta: { title: '域名（资产）' } },
        { path: 'link', name: 'asset-link', component: () => import('@netops/views/common/UnderConstruction.vue'), meta: { title: '链路信息' } },
        // 应用服务：应用系统、数据库实例
        { path: 'application', name: 'asset-application', component: () => import('@netops/views/common/UnderConstruction.vue'), meta: { title: '应用系统' } },
        { path: 'database', name: 'asset-database', component: () => import('@netops/views/common/UnderConstruction.vue'), meta: { title: '数据库实例' } },
        // 辅助页（网段的从属页面，不在导航挂出）
        { path: 'tags', name: 'asset-tags', component: () => import('@netops/views/ipam/tags.vue') },
        { path: 'tags/create', name: 'asset-tag-create', component: () => import('@netops/views/ipam/forms/TagForm.vue'), meta: { requiresOperator: true } },
        { path: 'tags/:id/edit', name: 'asset-tag-edit', component: () => import('@netops/views/ipam/forms/TagForm.vue'), meta: { requiresOperator: true } },
        { path: 'usage-trend', name: 'asset-usage-trend', component: () => import('@netops/views/ipam/usage-trend.vue') },
      ],
    },
    {
      path: '/topology',
      meta: { requiresAuth: true },
      children: [
        { path: '', name: 'topology', component: () => import('@netops/views/topology/topology.vue') },
        { path: 'edit', name: 'topology-edit', component: () => import('@netops/views/common/UnderConstruction.vue'), meta: { title: '拓扑编辑' } },
      ],
    },
    {
      // 配置域（对应导航「配置」分组）：基线 / 解析器 / 设备账号原挂 /devices，已并入
      path: '/config',
      meta: { requiresAuth: true },
      children: [
        { path: '', redirect: '/config/slb' },
        { path: 'slb', name: 'config-slb', component: () => import('@netops/views/config/lb/slb.vue') },
        { path: 'gslb', name: 'config-gslb', component: () => import('@netops/views/config/lb/gslb.vue') },
        { path: 'firewall', name: 'config-firewall', component: () => import('@netops/views/config/firewall/firewall.vue') },
        { path: 'routing-table', name: 'config-routing-table', component: () => import('@netops/views/config/network/routing-table.vue') },
        { path: 'arp-mac', name: 'config-arp-mac', component: () => import('@netops/views/config/network/arp-mac.vue') },
        { path: 'policy', name: 'config-policy', component: () => import('@netops/views/config/firewall/policy.vue') },
        { path: 'baseline', name: 'config-baseline', component: () => import('@netops/views/devices/baseline.vue') },
        { path: 'baseline/snmp/create', name: 'config-snmp-create', component: () => import('@netops/views/devices/forms/SnmpForm.vue'), meta: { requiresOperator: true } },
        { path: 'baseline/snmp/:id/edit', name: 'config-snmp-edit', component: () => import('@netops/views/devices/forms/SnmpForm.vue'), meta: { requiresOperator: true } },
        { path: 'baseline/ntp/create', name: 'config-ntp-create', component: () => import('@netops/views/devices/forms/NtpForm.vue'), meta: { requiresOperator: true } },
        { path: 'baseline/ntp/:id/edit', name: 'config-ntp-edit', component: () => import('@netops/views/devices/forms/NtpForm.vue'), meta: { requiresOperator: true } },
        { path: 'baseline/syslog/create', name: 'config-syslog-create', component: () => import('@netops/views/devices/forms/SyslogForm.vue'), meta: { requiresOperator: true } },
        { path: 'baseline/syslog/:id/edit', name: 'config-syslog-edit', component: () => import('@netops/views/devices/forms/SyslogForm.vue'), meta: { requiresOperator: true } },
        { path: 'parsers', name: 'config-parsers', component: () => import('@netops/views/devices/parsers.vue') },
        { path: 'accounts', name: 'config-accounts', component: () => import('@netops/views/devices/accounts.vue') },
      ],
    },
    {
      // 监控域（对应导航「监控」分组）
      path: '/monitor',
      meta: { requiresAuth: true },
      children: [
        { path: '', redirect: '/monitor/tasks' },
        { path: 'tasks', name: 'monitor-tasks', component: () => import('@netops/views/tasks/index.vue') },
        { path: 'status', name: 'monitor-status', component: () => import('@netops/views/tasks/monitor.vue') },
      ],
    },
    {
      path: '/docs',
      meta: { requiresAuth: true },
      children: [
        { path: '', redirect: '/docs/knowledge' },
        { path: 'knowledge', name: 'docs-knowledge', component: () => import('@netops/views/docs/knowledge.vue') },
        { path: 'temp', name: 'docs-temp', component: () => import('@netops/views/docs/temp.vue') },
        { path: 'spreadsheet', name: 'docs-spreadsheet', component: () => import('@netops/views/docs/spreadsheet.vue') },
        { path: 'spreadsheet/:id', name: 'docs-spreadsheet-edit', component: () => import('@netops/views/docs/spreadsheet-edit.vue') },
      ],
    },
    {
      path: '/tools',
      meta: { requiresAuth: true },
      children: [
        { path: '', redirect: '/tools/path-trace' },
        { path: 'path-trace', name: 'tools-path-trace', component: () => import('@netops/views/tools/path-trace.vue') },
        { path: 'rack-view', name: 'tools-rack-view', component: () => import('@netops/views/tools/rack-view.vue') },
        { path: 'subnet-calc', name: 'tools-subnet-calc', component: () => import('@netops/views/tools/subnet-calc.vue') },
        { path: 'dns-query', name: 'tools-dns-query', component: () => import('@netops/views/tools/dns-query.vue') },
        { path: 'internet-asset', name: 'tools-internet-asset', component: () => import('@netops/views/tools/internet-asset.vue') },
        { path: 'parser-mapping', name: 'tools-parser-mapping', component: () => import('@netops/views/tools/parser-mapping.vue') },
      ],
    },
    // —— 旧路径兼容（按导航分组重排前的地址，收藏夹 / 外部链接仍可访问）——
    { path: '/devices', redirect: '/asset/devices' },
    { path: '/devices/create', redirect: '/asset/devices/create' },
    { path: '/devices/:id/edit', redirect: legacyRedirect((to) => `/asset/devices/${to.params.id}/edit`) },
    { path: '/devices/:id/config', redirect: legacyRedirect((to) => `/asset/devices/${to.params.id}/config`) },
    { path: '/devices/:id/history', redirect: legacyRedirect((to) => `/asset/devices/${to.params.id}/history`) },
    { path: '/devices/:id/compare', redirect: legacyRedirect((to) => `/asset/devices/${to.params.id}/compare`) },
    { path: '/devices/interfaces', redirect: '/asset/interfaces' },
    { path: '/devices/interfaces/:id/edit', redirect: legacyRedirect((to) => `/asset/interfaces/${to.params.id}/edit`) },
    { path: '/devices/vlans', redirect: '/asset/vlans' },
    { path: '/devices/baseline', redirect: '/config/baseline' },
    { path: '/devices/baseline/snmp/create', redirect: '/config/baseline/snmp/create' },
    { path: '/devices/baseline/snmp/:id/edit', redirect: legacyRedirect((to) => `/config/baseline/snmp/${to.params.id}/edit`) },
    { path: '/devices/baseline/ntp/create', redirect: '/config/baseline/ntp/create' },
    { path: '/devices/baseline/ntp/:id/edit', redirect: legacyRedirect((to) => `/config/baseline/ntp/${to.params.id}/edit`) },
    { path: '/devices/baseline/syslog/create', redirect: '/config/baseline/syslog/create' },
    { path: '/devices/baseline/syslog/:id/edit', redirect: legacyRedirect((to) => `/config/baseline/syslog/${to.params.id}/edit`) },
    { path: '/devices/parsers', redirect: '/config/parsers' },
    { path: '/devices/accounts', redirect: '/config/accounts' },
    { path: '/ipam', redirect: '/asset/subnets' },
    { path: '/ipam/subnets', redirect: '/asset/subnets' },
    { path: '/ipam/subnets/create', redirect: '/asset/subnets/create' },
    { path: '/ipam/subnets/:id/edit', redirect: legacyRedirect((to) => `/asset/subnets/${to.params.id}/edit`) },
    { path: '/ipam/ip-addresses', redirect: '/asset/ip-addresses' },
    { path: '/ipam/ip-addresses/create', redirect: '/asset/ip-addresses/create' },
    { path: '/ipam/ip-addresses/:id/edit', redirect: legacyRedirect((to) => `/asset/ip-addresses/${to.params.id}/edit`) },
    { path: '/ipam/tags', redirect: '/asset/tags' },
    { path: '/ipam/tags/create', redirect: '/asset/tags/create' },
    { path: '/ipam/tags/:id/edit', redirect: legacyRedirect((to) => `/asset/tags/${to.params.id}/edit`) },
    { path: '/ipam/usage-trend', redirect: '/asset/usage-trend' },
    { path: '/tasks', redirect: '/monitor/tasks' },
    { path: '/tasks/monitor', redirect: '/monitor/status' },
    // 旧 /tools/spreadsheet* 路径兼容（表格编辑器已移入「文档」菜单）
    { path: '/tools/spreadsheet', redirect: '/docs/spreadsheet' },
    { path: '/tools/spreadsheet/:id', redirect: '/docs/spreadsheet/:id' },
    // 兜底：未注册路径（含 /login——它是不注册路由的"伪路径"，靠下面的守卫与 App.vue 协作）。
    // 必须用「匹配组件」而不是 redirect：
    //   ① redirect 到 '/' 会与守卫的 return '/login' 互相触发，形成无限重定向；
    //   ② 401 跳转靠 pathname 能停在 /login 防循环（见 api/index.ts），redirect 会把 URL 改掉；
    // 已登录访问乱路径时渲染总览页，避免 matched=[] 白屏。
    { path: '/:pathMatch(.*)*', meta: { requiresAuth: true }, component: () => import('@netops/views/Home.vue') },
  ],
})

router.beforeEach(async (to) => {
  // /login 已由兜底路由命中，不要再重定向它自己（return '/login' 会与自身相撞）
  if (to.path === '/login') return true
  if (to.meta.requiresAuth && !getToken()) {
    // 跳到 /login 伪路径后，App.vue 按「未登录」兜底渲染静态引入的 Login。
    // 必须用字符串路径——命名路由 'login' 不存在，resolve 会直接抛错。
    return '/login'
  }
  // 写表单路由（新建 / 编辑）：普通用户直接输 URL 也进不去，避免填完才被后端 403
  if (to.meta.requiresOperator) {
    const auth = useAuthStore()
    // 刷新页面时 user 还没拉回来（App.vue 的 onMounted 是异步的），先补一次
    if (!auth.user) await auth.fetchUser()
    if (!auth.canWrite) {
      ElMessage.warning('需要操作员权限')
      return '/'
    }
  }
})

export default router
