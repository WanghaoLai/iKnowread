import { ref } from 'vue'

// 分页列表加载的统一骨架：请求序号防止慢的旧响应覆盖新响应，
// 可选 AbortController 取消旧请求，loading 态贯穿请求生命周期。
// fetcher 收到 (signal, ...args)；返回 null 表示已被更新请求取代或失败。
export function useListLoader(fetcher, {
  cancellable = false,
  onError = null,
} = {}) {
  const loading = ref(false)
  let sequence = 0
  let controller = null

  async function load(...args) {
    if (cancellable) {
      controller?.abort()
      controller = new AbortController()
    }
    const current = ++sequence
    loading.value = true
    try {
      const response = await fetcher(controller?.signal, ...args)
      if (sequence !== current) return null
      return response
    } catch (error) {
      onError?.(error)
      return null
    } finally {
      if (sequence === current) loading.value = false
    }
  }

  // 使仍在途的结果失效（组件卸载时调用，防止过期赋值与取消提示）
  function invalidate() {
    sequence += 1
    controller?.abort()
  }

  return { loading, load, invalidate }
}
