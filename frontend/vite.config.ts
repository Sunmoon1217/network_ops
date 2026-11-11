import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

// 「只生成 d.ts」模式：`pnpm gen-dts` 用它，`pnpm build` / `pnpm type-check` / pre-commit 都会先跑。
//
// 为什么需要：auto-imports.d.ts / components.d.ts 由这两个插件在 **buildEnd** 写出（dev 下
// 靠 transform 的节流写入，只覆盖被请求到的模块，装不全），而 `vue-tsc` 必须要它们——
// 缺失时 `ref` / `computed` / `ElMessage` 全被判成 "Cannot find name"。
//
// 本模式只为了让插件跑完一轮完整生命周期：产物丢 node_modules/.cache（不碰 dist）、关掉压缩
// 与 sourcemap。注意它仍是一次完整打包，所以 `pnpm build` 的日志里会出现两次 "built in"
// （一次本模式、一次正式打包）——这是「每次重建声明」的代价。
const DTS_ONLY_MODE = 'gen-dts'

export default defineConfig(({ mode }) => {
  const dtsOnly = mode === DTS_ONLY_MODE

  return {
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
