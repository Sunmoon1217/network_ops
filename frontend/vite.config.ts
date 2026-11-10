import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig({
  plugins: [
    vue(),
    AutoImport({
      imports: [
        'vue',
        'vue-router',
        'pinia',
        {
          'element-plus': ['ElMessage', 'ElMessageBox', 'ElNotification'],
        },
      ],
      dts: './auto-imports.d.ts',
    }),
    Components({
      resolvers: [ElementPlusResolver({ importStyle: 'css' })],
      dts: './components.d.ts',
    }),
  ],
  resolve: {
    // '@' 指向共享层；两个应用各自用语义化别名，避免共享层反向依赖 app
    alias: {
      '@': fileURLToPath(new URL('./src/shared', import.meta.url)),
      '@netops': fileURLToPath(new URL('./src/netops', import.meta.url)),
      '@dashboard': fileURLToPath(new URL('./src/dashboard', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // MCP 端点（Streamable HTTP）。不代理的话 /mcp 会落到 history fallback
      // 返回 index.html，被 Vue Router 当成未知路由 → 守卫跳登录。
      '/mcp': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      input: {
        netops: fileURLToPath(new URL('./index.html', import.meta.url)),
        dashboard: fileURLToPath(new URL('./dashboard.html', import.meta.url)),
      },
    },
  },
})
