import { ref } from 'vue'

// 分页列表加载的统一骨架：请求序号防止慢的旧响应覆盖新响应，
// 可选 AbortController 取消旧请求，loading 态贯穿请求生命周期。
// fetcher 收到 ({ signal, skipErrorToast }, ...args)。列表加载器独占错误提示，
// 因而旧请求即使在取消前失败，也不会先被全局拦截器弹出过期错误。
export function isCanceledRequest(error) {
  return error?.code === 'ERR_CANCELED' || error?.name === 'AbortError'
}

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
      const response = await fetcher({
        signal: controller?.signal,
        skipErrorToast: true,
      }, ...args)
      if (sequence !== current) return null
      return response
    } catch (error) {
      if (sequence !== current || isCanceledRequest(error)) return null
      await onError?.(error)
      return null
    } finally {
      if (sequence === current) loading.value = false
    }
  }

  // 使仍在途的结果失效（组件卸载时调用，防止过期赋值与错误提示）
  function invalidate() {
    sequence += 1
    controller?.abort()
  }

  return { loading, load, invalidate }
}
