export const ANNOUNCEMENT_STATUS = Object.freeze({
  draft: { label: '草稿', type: 'info' },
  published: { label: '已发布', type: 'success' },
  offline: { label: '已下架', type: 'warning' },
})

export function announcementStatus(status) {
  return ANNOUNCEMENT_STATUS[status] || { label: status || '未知', type: 'info' }
}

export function applyAnnouncementRead(items, announcementId) {
  let changed = false
  const next = items.map(item => {
    if (item.id !== announcementId || item.is_read) return item
    changed = true
    return { ...item, is_read: true }
  })
  return { items: next, changed }
}

export function applyAllAnnouncementsRead(items) {
  return items.map(item => item.is_read ? item : { ...item, is_read: true })
}
