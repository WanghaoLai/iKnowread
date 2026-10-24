import { onBeforeUnmount, onMounted, ref } from 'vue'
import {
  listAnnouncements,
  markAllAnnouncementsRead,
  markAnnouncementRead,
} from '@/api/announcements'
import { applyAllAnnouncementsRead, applyAnnouncementRead } from '@/utils/announcements'

const REFRESH_INTERVAL_MS = 60_000

export function useAnnouncements() {
  const items = ref([])
  const unreadCount = ref(0)
  const loading = ref(false)
  const error = ref(false)
  const mutating = ref(false)
  let timer = null
  let sequence = 0
  let controller = null

  async function refresh({ silent = false } = {}) {
    controller?.abort()
    controller = new AbortController()
    const current = ++sequence
    if (!silent) loading.value = true
    try {
      const response = await listAnnouncements(
        { pageNum: 1, pageSize: 50 },
        { signal: controller.signal, skipErrorToast: true },
      )
      if (current !== sequence) return
      items.value = response.data?.list || []
      unreadCount.value = Number(response.data?.unread_count || 0)
      error.value = false
    } catch (requestError) {
      if (requestError?.code !== 'ERR_CANCELED' && current === sequence) error.value = true
    } finally {
      // A silent refresh can replace the initial visible request (for example,
      // when the user opens the panel immediately), so the latest request must
      // always release an existing loading state.
      if (current === sequence) loading.value = false
    }
  }

  async function read(item) {
    if (!item || item.is_read || mutating.value) return
    mutating.value = true
    try {
      await markAnnouncementRead(item.id, { skipErrorToast: true })
      const result = applyAnnouncementRead(items.value, item.id)
      items.value = result.items
      if (result.changed) unreadCount.value = Math.max(0, unreadCount.value - 1)
      error.value = false
    } catch (_) {
      error.value = true
    } finally {
      mutating.value = false
    }
  }

  async function readAll() {
    if (!unreadCount.value || mutating.value) return
    mutating.value = true
    try {
      await markAllAnnouncementsRead({ skipErrorToast: true })
      items.value = applyAllAnnouncementsRead(items.value)
      unreadCount.value = 0
      error.value = false
    } catch (_) {
      error.value = true
    } finally {
      mutating.value = false
    }
  }

  const handleFocus = () => refresh({ silent: true })

  onMounted(() => {
    refresh()
    timer = window.setInterval(() => refresh({ silent: true }), REFRESH_INTERVAL_MS)
    window.addEventListener('focus', handleFocus)
  })

  onBeforeUnmount(() => {
    sequence += 1
    controller?.abort()
    window.clearInterval(timer)
    window.removeEventListener('focus', handleFocus)
  })

  return { items, unreadCount, loading, error, mutating, refresh, read, readAll }
}
