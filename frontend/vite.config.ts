import { fileURLToPath, URL } from 'node:url'
import type { Plugin } from 'vite'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

// 「只生成 d.ts」模式：`pnpm gen-dts` 用它（`pnpm type-check` 与 pre-commit 会先跑）。
// auto-imports.d.ts / components.d.ts 只在 buildEnd 写全量，单独跑 vue-tsc 前必须先补一份，
// 否则 ref / ElMessage 全被判成 Cannot find name；产物丢 node_modules/.cache，不污染 dist。
const DTS_ONLY_MODE = 'gen-dts'

// dev 下把 /dashboard 归一到 dashboard.html，并让 / 302 到大屏，与 nginx / Django 一致。
// configureServer 的中间件早于 Vite 自带 SPA fallback，否则会被改写成 /index.html。
const dashboardEntryPlugin: Plugin = {
  name: 'netops-dashboard-entry',
  configureServer: (server) => {
    server.middlewares.use((req, res, next) => {
      const [pathname, query] = (req.url ?? '').split('?')
      if (pathname === '/dashboard' || pathname === '/dashboard/') {
        req.url = query === undefined ? '/dashboard.html' : `/dashboard.html?${query}`
      } else if (pathname === '/') {
        res.writeHead(302, { Location: '/dashboard' })
        res.end()
        return
      }
      next()
    })
  },
}

export default defineConfig(({ mode }) => {
  const dtsOnly = mode === DTS_ONLY_MODE

  return {
    plugins: [
      vue(),
      dashboardEntryPlugin,
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
      // gen-dts 模式的产物没人用，扔缓存目录并省掉压缩/体积统计，别污染 dist
      ...(dtsOnly && {
        outDir: 'node_modules/.cache/netops-dts',
        emptyOutDir: true,
        minify: false,
        sourcemap: false,
        reportCompressedSize: false,
      }),
    },
  }
})
