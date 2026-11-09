import { ref, watch } from 'vue'
import type { Ref } from 'vue'

/**
 * 页面级共享搜索词：把一个关键词同步写入多个 useCrudApi 的 search。
 *
 * 用于同一页面多个 tab 各自持有独立 useCrudApi 实例的场景（负载均衡 / 域名解析）：
 * 每个 tab 的 search 由 useCrudApi 内部 watch 触发防抖请求，这里只负责同步取值。
 *
 * @param targets 各 tab useCrudApi 返回的 search ref
 * @returns 绑定到搜索框的 keyword ref
 */
export const useSearchSync = (...targets: Ref<string>[]) => {
  const keyword = ref('')
  watch(keyword, (v) => {
    for (const t of targets) t.value = v
  })
  return keyword
}
