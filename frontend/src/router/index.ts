import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('@/views/Welcome.vue'),
    },
    {
      path: '/devices',
      name: 'devices',
      component: () => import('@/views/DeviceList.vue'),
    },
    {
      path: '/devices/create',
      name: 'device-create',
      component: () => import('@/views/DeviceCreate.vue'),
    },
    {
      path: '/devices/:id/config',
      name: 'device-config',
      component: () => import('@/views/DeviceConfigView.vue'),
    },
    {
      path: '/devices/:id/history',
      name: 'device-config-history',
      component: () => import('@/views/DeviceConfigHistoryView.vue'),
    },
    {
      path: '/config/interfaces',
      name: 'interfaces',
      component: () => import('@/views/InterfaceManagementView.vue'),
    },
  ],
})

export default router
