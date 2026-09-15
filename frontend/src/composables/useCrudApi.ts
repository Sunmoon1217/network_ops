import { ref, computed, watch, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

type Fetcher = () => Promise<any>

/**
 * 列表页数据获取 + 服务端分页的组合式函数。
 *
 * 约定：页面在自己的 fetcher 里用 `pageParams()` 拼装分页 / 搜索参数，
 * 例如 `fetchData(() => api.get('/api/assets/vlans/', { params: pageParams({ device }) }))`。
 *
 * 分页、搜索由服务端完成（后端已启用 PageNumberPagination + SearchFilter），
 * 因此不要再对返回结果做本地过滤，否则只会过滤当前页。
 *
 * @param _searchFields 已废弃：搜索改由后端 search_fields 处理，仅为兼容旧调用保留
 */
export function useCrudApi<T extends Record<string, any> = any>(_searchFields: string[] = []) {
  const data = ref<T[]>([]) as any
  const loading = ref(false)
  const search = ref('')
  const page = ref(1)
  const pageSize = ref(50)
  const total = ref(0)

  let lastFetcher: Fetcher | null = null
  let searchTimer: ReturnType<typeof setTimeout> | null = null

  /** 兼容裸数组与 {count, next, previous, results} 两种响应结构 */
  function applyResponse(res: any) {
    const payload = res?.data ?? res
    if (Array.isArray(payload)) {
      data.value = payload
      total.value = payload.length
      return
    }
    if (Array.isArray(payload?.results)) {
      data.value = payload.results
      total.value = Number(payload.count ?? payload.results.length)
      return
    }
    data.value = []
    total.value = 0
  }

  async function run(fetcher: Fetcher) {
    lastFetcher = fetcher
    loading.value = true
    try {
      applyResponse(await fetcher())
    } catch {
      ElMessage.error('加载失败')
    } finally {
      loading.value = false
    }
  }

  /** 首次加载或条件变化后重新构造请求时调用 */
  function fetchData(fetcher: Fetcher) {
    return run(fetcher)
  }

  /** 用上一次的请求重新拉取（翻页 / 搜索 / 过滤器变化时使用） */
  function refetch() {
    return lastFetcher ? run(lastFetcher) : Promise.resolve()
  }

  /** 拼装分页与搜索参数，页面再合并自己的过滤条件 */
  function pageParams(extra: Record<string, any> = {}) {
    const params: Record<string, any> = { page: page.value, page_size: pageSize.value, ...extra }
    if (search.value) params.search = search.value
    return params
  }

  /** 回到第一页并重新拉取（过滤器变化时使用） */
  function resetAndFetch() {
    page.value = 1
    return refetch()
  }

  // 搜索走服务端，输入防抖 300ms
  watch(search, () => {
    if (searchTimer) clearTimeout(searchTimer)
    searchTimer = setTimeout(() => {
      page.value = 1
      refetch()
    }, 300)
  })

  onUnmounted(() => {
    if (searchTimer) clearTimeout(searchTimer)
  })

  async function handleSave(apiFn: () => Promise<any>, onSuccess?: () => void) {
    try {
      await apiFn()
      ElMessage.success('保存成功')
      onSuccess?.()
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || e?.response?.data?.name?.[0] || '保存失败')
    }
  }

  async function handleDelete(name: string, apiFn: () => Promise<any>, onSuccess?: () => void) {
    await ElMessageBox.confirm(`确认删除 ${name}？`, '提示', { type: 'warning' })
    try {
      await apiFn()
      ElMessage.success('已删除')
      onSuccess?.()
    } catch {
      ElMessage.error('删除失败')
    }
  }

  return {
    data,
    loading,
    search,
    page,
    pageSize,
    total,
    // 兼容旧页面：现在等于 data（搜索/过滤均由服务端完成）
    filteredData: computed(() => data.value),
    fetchData,
    refetch,
    pageParams,
    resetAndFetch,
    handleSave,
    handleDelete,
  }
}
