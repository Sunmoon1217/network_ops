import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from '@/utils/token'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/login/Login.vue'),
      meta: { skipLayout: true },
    },
    {
      path: '/',
      name: 'home',
      component: () => import('@/views/dashboard/Home.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/devices',
      component: () => import('@/views/devices/index.vue'),
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
      component: () => import('@/views/devices/index.vue'),
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
      component: () => import('@/views/devices/index.vue'),
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
      component: () => import('@/views/devices/index.vue'),
      meta: { requiresAuth: true },
      children: [
        { path: '', name: 'topology', component: () => import('@/views/tools/topology.vue') },
      ],
    },
    {
      path: '/tools',
      component: () => import('@/views/devices/index.vue'),
      meta: { requiresAuth: true },
      children: [
        { path: '', redirect: '/tools/path-trace' },
        { path: 'path-trace', name: 'tools-path-trace', component: () => import('@/views/tools/path-trace.vue') },
        { path: 'rack-view', name: 'tools-rack-view', component: () => import('@/views/tools/rack-view.vue') },
        { path: 'subnet-calc', name: 'tools-subnet-calc', component: () => import('@/views/tools/subnet-calc.vue') },
        { path: 'dns-query', name: 'tools-dns-query', component: () => import('@/views/tools/dns-query.vue') },

      ],
    },
  ],
})

router.beforeEach((to) => {
  if (to.meta.requiresAuth && !getToken()) {
    return { name: 'login' }
  }
})

export default router
