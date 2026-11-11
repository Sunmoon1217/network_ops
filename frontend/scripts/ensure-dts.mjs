// 只在缺失时补齐 auto-imports.d.ts / components.d.ts（供 `pnpm type-check` 用）。
//
// 为什么不每次都生成：两个声明文件由 vite 插件在 **buildEnd** 写出，生成一次等于跑一遍
// 打包（约 3 秒）。`pnpm build` 自己就会写，所以日常只需在「新 clone / 改过插件 imports
// 或 resolvers」之后补一次——有就跳过，别让 type-check 也变成两次构建。
//
// 用法：node scripts/ensure-dts.mjs（已挂在 type-check 前面）；想强制重生成用 pnpm gen-dts。
import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const DTS_FILES = ['auto-imports.d.ts', 'components.d.ts']

const missing = DTS_FILES.filter((name) => !existsSync(resolve(ROOT, name)))

if (missing.length === 0) {
  console.log('[gen-dts] auto-imports.d.ts / components.d.ts 已存在，跳过')
  process.exit(0)
}

console.log(`[gen-dts] 缺少 ${missing.join(' / ')}，先跑一次 vite build --mode gen-dts 补齐…`)

const result = spawnSync(process.execPath, [resolve(ROOT, 'node_modules/vite/bin/vite.js'), 'build', '--mode', 'gen-dts'], {
  cwd: ROOT,
  stdio: 'inherit',
})

process.exit(result.status ?? 1)
