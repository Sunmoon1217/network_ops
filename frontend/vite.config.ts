import { fileURLToPath, URL } from 'node:url'
import type { Plugin } from 'vite'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

// 「只生成 d.ts」模式：`pnpm gen-dts` 用它。
//
// 为什么需要：auto-imports.d.ts / components.d.ts 由这两个插件在 **buildEnd** 写出（dev
// 下靠 transform 的节流写入），而 `pnpm build` 的第一步是 `vue-tsc --noEmit`——新 clone
// 上这两个文件还不存在（它们在 .gitignore 里），vue-tsc 会把 `ref` / `computed` /
// `ElMessage` 全判成 "Cannot find name"。所以 build 前先单独跑一次本模式，把 d.ts 生成出来。
//
// 本模式**只为了让插件跑完生命周期**：产物丢进 node_modules/.cache（不碰 dist）、关掉压缩与
// sourcemap（这一步只为写文件，不需要优化过的产物）。
const DTS_ONLY_MODE = 'gen-dts'

// dev 下 /dashboard 会被 Vite 自带的 SPA fallback 改写成 /index.html（主站），
// 与生产 nginx / Django 的「大屏单独处理」不一致。configureServer 里直接注册中间件
// 发生在 Vite 内部中间件之前，把友好 URL 归一到第二个入口 dashboard.html。
const dashboardEntryPlugin: Plugin = {
  name: 'netops-dashboard-entry',
  configureServer: (server) => {
    server.middlewares.use((req, _res, next) => {
      const [pathname, query] = (req.url ?? '').split('?')
      if (pathname === '/dashboard' || pathname === '/dashboard/') {
        req.url = query === undefined ? '/dashboard.html' : `/dashboard.html?${query}`
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
