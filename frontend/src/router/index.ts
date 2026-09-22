import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from '@/utils/token'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    // {
    //   path: '/login',
    //   name: 'login',
    //   component: () => import('@/views/auth/Login.vue'),
    //   meta: { skipLayout: true },
    // },
    {
      path: '/register',
      name: 'register',
      component: () => import('@/views/auth/Register.vue'),
      meta: { skipLayout: true },
    },
    {
      path: '/auth/change-password',
      name: 'change-password',
      component: () => import('@/views/auth/ChangePassword.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/',
      name: 'home',
      component: () => import('@/views/Home.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/devices',
      // component: () => import('@/views/devices/index.vue'),
      meta: { requiresAuth: true },
      children: [
        { path: '', name: 'device-list', component: () => import('@/views/devices/list.vue') },
        { path: 'create', name: 'device-create', component: () => import('@/views/devices/forms/DeviceForm.vue') },
        { path: ':id/edit', name: 'device-edit', component: () => import('@/views/devices/forms/DeviceForm.vue') },
        { path: ':id/config', name: 'device-config', component: () => import('@/views/devices/config.vue') },
        { path: ':id/history', name: 'device-history', component: () => import('@/views/devices/history.vue') },
        { path: ':id/compare', name: 'device-compare', component: () => import('@/views/devices/compare.vue') },
        { path: 'interfaces', name: 'device-interfaces', component: () => import('@/views/devices/interfaces.vue') },
        { path: 'interfaces/:id/edit', name: 'interface-edit', component: () => import('@/views/devices/forms/InterfaceForm.vue') },
        { path: 'baseline', name: 'device-baseline', component: () => import('@/views/devices/baseline.vue') },
        { path: 'baseline/snmp/create', name: 'snmp-create', component: () => import('@/views/devices/forms/SnmpForm.vue') },
        { path: 'baseline/snmp/:id/edit', name: 'snmp-edit', component: () => import('@/views/devices/forms/SnmpForm.vue') },
        { path: 'baseline/ntp/create', name: 'ntp-create', component: () => import('@/views/devices/forms/NtpForm.vue') },
        { path: 'baseline/ntp/:id/edit', name: 'ntp-edit', component: () => import('@/views/devices/forms/NtpForm.vue') },
        { path: 'baseline/syslog/create', name: 'syslog-create', component: () => import('@/views/devices/forms/SyslogForm.vue') },
        { path: 'baseline/syslog/:id/edit', name: 'syslog-edit', component: () => import('@/views/devices/forms/SyslogForm.vue') },
        { path: 'parsers', name: 'device-parsers', component: () => import('@/views/devices/parsers.vue') },
        { path: 'accounts', name: 'device-accounts', component: () => import('@/views/devices/accounts.vue') },
        { path: 'vlans', name: 'device-vlans', component: () => import('@/views/devices/vlans.vue') },
      ],
    },
    {
      path: '/config',
      // component: () => import('@/views/devices/index.vue'),
      meta: { requiresAuth: true },
      children: [
        { path: '', redirect: '/config/slb' },
        { path: 'slb', name: 'config-slb', component: () => import('@/views/config/lb/slb.vue') },
        { path: 'gslb', name: 'config-gslb', component: () => import('@/views/config/lb/gslb.vue') },
        { path: 'firewall', name: 'config-firewall', component: () => import('@/views/config/firewall/firewall.vue') },
        { path: 'routing-table', name: 'config-routing-table', component: () => import('@/views/config/network/routing-table.vue') },
        { path: 'arp-mac', name: 'config-arp-mac', component: () => import('@/views/config/network/arp-mac.vue') },
        { path: 'policy', name: 'config-policy', component: () => import('@/views/config/firewall/policy.vue') },
      ],
    },
    {
      path: '/ipam',
      // component: () => import('@/views/devices/index.vue'),
      meta: { requiresAuth: true },
      children: [
        { path: '', redirect: '/ipam/subnets' },
        { path: 'subnets', name: 'ipam-subnets', component: () => import('@/views/ipam/index.vue') },
        { path: 'subnets/create', name: 'subnet-create', component: () => import('@/views/ipam/forms/SubnetForm.vue') },
        { path: 'subnets/:id/edit', name: 'subnet-edit', component: () => import('@/views/ipam/forms/SubnetForm.vue') },
        { path: 'ip-addresses', name: 'ipam-ip-addresses', component: () => import('@/views/ipam/ip-address.vue') },
        { path: 'ip-addresses/create', name: 'ip-create', component: () => import('@/views/ipam/forms/IpAddressForm.vue') },
        { path: 'ip-addresses/:id/edit', name: 'ip-edit', component: () => import('@/views/ipam/forms/IpAddressForm.vue') },
        { path: 'tags', name: 'ipam-tags', component: () => import('@/views/ipam/tags.vue') },
        { path: 'tags/create', name: 'tag-create', component: () => import('@/views/ipam/forms/TagForm.vue') },
        { path: 'usage-trend', name: 'ipam-usage-trend', component: () => import('@/views/ipam/usage-trend.vue') },
        { path: 'tags/:id/edit', name: 'tag-edit', component: () => import('@/views/ipam/forms/TagForm.vue') },
      ],
    },
    {
      path: '/topology',
      // component: () => import('@/views/devices/index.vue'),
      meta: { requiresAuth: true },
      children: [
        { path: '', name: 'topology', component: () => import('@/views/topology/topology.vue') },
      ],
    },
    {
      path: '/tasks',
      // component: () => import('@/views/devices/index.vue'),
      meta: { requiresAuth: true },
      children: [
        { path: '', name: 'task-list', component: () => import('@/views/tasks/index.vue') },
      ],
    },
    {
      path: '/tools',
      // component: () => import('@/views/devices/index.vue'),
      meta: { requiresAuth: true },
      children: [
        { path: '', redirect: '/tools/path-trace' },
        { path: 'path-trace', name: 'tools-path-trace', component: () => import('@/views/tools/path-trace.vue') },
        { path: 'rack-view', name: 'tools-rack-view', component: () => import('@/views/tools/rack-view.vue') },
        { path: 'subnet-calc', name: 'tools-subnet-calc', component: () => import('@/views/tools/subnet-calc.vue') },
        { path: 'dns-query', name: 'tools-dns-query', component: () => import('@/views/tools/dns-query.vue') },
        { path: 'internet-asset', name: 'tools-internet-asset', component: () => import('@/views/tools/internet-asset.vue') },
        { path: 'parser-mapping', name: 'tools-parser-mapping', component: () => import('@/views/tools/parser-mapping.vue') },

      ],
    },
    // 兜底：未注册路径（含 /login——它是不注册路由的"伪路径"，靠下面的守卫与 App.vue 协作）。
    // 必须用「匹配组件」而不是 redirect：
    //   ① redirect 到 '/' 会与守卫的 return '/login' 互相触发，形成无限重定向；
    //   ② 401 跳转靠 pathname 能停在 /login 防循环（见 api/index.ts），redirect 会把 URL 改掉；
    // 已登录访问乱路径时渲染总览页，避免 matched=[] 白屏。
    { path: '/:pathMatch(.*)*', meta: { requiresAuth: true }, component: () => import('@/views/Home.vue') },
  ],
})

router.beforeEach((to) => {
  // /login 已由兜底路由命中，不要再重定向它自己（return '/login' 会与自身相撞）
  if (to.path === '/login') return true
  if (to.meta.requiresAuth && !getToken()) {
    // 跳到 /login 伪路径后，App.vue 按「未登录」兜底渲染静态引入的 Login。
    // 必须用字符串路径——命名路由 'login' 不存在，resolve 会直接抛错。
    return '/login'
  }
})

export default router
